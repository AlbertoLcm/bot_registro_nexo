"""Interfaz gráfica de escritorio para el RPA."""
import asyncio
import queue
import re
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk

from app.config import BASE_DIR, INPUT_JSON_FILE
from app.core.logging import _error, _info, _ok, _section, _warn
from app.ui.console import RedirectConsole
from app.ui.theme import (
    BBVA_NAVY, BBVA_CORE_BLUE, BBVA_MEDIUM_BLUE, BBVA_AQUA,
    BBVA_BG_LIGHT, BBVA_WHITE, BBVA_TEXT_PRIMARY, BBVA_CONSOLE_BG,
)
from app.workflows.orchestrator import ejecutar_rpa_async


class BBVARpaApp(ctk.CTk):
    """Ventana principal de la interfaz gráfica estilo BBVA."""

    ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    def __init__(self):
        super().__init__()

        # Configuración general de la ventana
        ctk.set_appearance_mode("light")
        self.title("BBVA | Automatización RPA - Registro de Oficios SUGO")
        self.geometry("920x660")
        self.minsize(820, 580)
        self.configure(fg_color=BBVA_BG_LIGHT)

        # Estado de la aplicación
        self.selected_json_path = tk.StringVar(value=str(INPUT_JSON_FILE))
        self.modo_oculto_var = tk.BooleanVar(value=False)
        self.is_running = False
        self.log_queue = queue.Queue()

        # Redirección de logs (stdout/stderr) hacia la consola GUI
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        sys.stdout = RedirectConsole(self.log_queue, self.original_stdout)
        sys.stderr = RedirectConsole(self.log_queue, self.original_stderr)

        self._construir_interfaz()
        self._procesar_cola_logs()

        # Mensaje inicial de bienvenida en la consola
        _section(" Consola RPA SUGO Inicializada ", "Seleccione un archivo JSON y configure el modo de ejecución")
        if INPUT_JSON_FILE.exists():
            _ok(f"Archivo por defecto detectado: {INPUT_JSON_FILE.name}")
        else:
            _warn("Seleccione un archivo JSON válido para comenzar la carga.")

    def _construir_interfaz(self):
        """Construye todos los bloques visuales con el diseño de BBVA."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ---------------------------------------------------------
        # 1. HEADER CORPORATIVO BBVA
        # ---------------------------------------------------------
        header_frame = ctk.CTkFrame(
            self,
            fg_color=BBVA_NAVY,
            corner_radius=0,
            height=76
        )
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        # Franja decorativa superior Aqua
        aqua_bar = ctk.CTkFrame(header_frame, fg_color=BBVA_AQUA, height=4, corner_radius=0)
        aqua_bar.grid(row=0, column=0, columnspan=3, sticky="ew")

        # Logo / Marca BBVA
        brand_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        brand_frame.grid(row=1, column=0, padx=(28, 14), pady=14, sticky="w")

        lbl_bbva = ctk.CTkLabel(
            brand_frame,
            text="BBVA",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=BBVA_WHITE
        )
        lbl_bbva.pack(side="left")

        sep_bar = ctk.CTkFrame(brand_frame, fg_color=BBVA_AQUA, width=3, height=26)
        sep_bar.pack(side="left", padx=14)

        title_sub_frame = ctk.CTkFrame(brand_frame, fg_color="transparent")
        title_sub_frame.pack(side="left")

        lbl_app_title = ctk.CTkLabel(
            title_sub_frame,
            text="RPA Gestor de Oficios SUGO",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=BBVA_WHITE
        )
        lbl_app_title.pack(anchor="w")

        lbl_app_sub = ctk.CTkLabel(
            title_sub_frame,
            text="Automatización de Alta, Personas y Carga Documental",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#A5B8D1"
        )
        lbl_app_sub.pack(anchor="w")

        # Badge de estado en el Header
        self.status_badge = ctk.CTkLabel(
            header_frame,
            text="●  SISTEMA LISTO",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=BBVA_AQUA,
            fg_color="#0D3166",
            corner_radius=16,
            padx=14,
            pady=6
        )
        self.status_badge.grid(row=1, column=2, padx=28, pady=14, sticky="e")

        # ---------------------------------------------------------
        # 2. TARJETA DE CONTROLES Y CONFIGURACIÓN
        # ---------------------------------------------------------
        control_card = ctk.CTkFrame(
            self,
            fg_color=BBVA_WHITE,
            corner_radius=10,
            border_width=1,
            border_color="#DCE3EB"
        )
        control_card.grid(row=1, column=0, padx=24, pady=(20, 12), sticky="ew")
        control_card.grid_columnconfigure(0, weight=1)

        # Fila Superior: Selección de Archivo JSON
        file_section = ctk.CTkFrame(control_card, fg_color="transparent")
        file_section.grid(row=0, column=0, padx=22, pady=(18, 12), sticky="ew")
        file_section.grid_columnconfigure(0, weight=1)

        lbl_json = ctk.CTkLabel(
            file_section,
            text="ARCHIVO JSON DE CARGA (OFICIOS)",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=BBVA_CORE_BLUE
        )
        lbl_json.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.entry_json = ctk.CTkEntry(
            file_section,
            textvariable=self.selected_json_path,
            height=38,
            corner_radius=6,
            border_width=1,
            border_color="#C4CFD9",
            fg_color="#F9FBFC",
            text_color=BBVA_TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        self.entry_json.grid(row=1, column=0, sticky="ew", padx=(0, 12))

        self.btn_browse = ctk.CTkButton(
            file_section,
            text="Seleccionar JSON",
            command=self._seleccionar_archivo_json,
            height=38,
            width=155,
            corner_radius=6,
            fg_color=BBVA_CORE_BLUE,
            hover_color=BBVA_MEDIUM_BLUE,
            text_color=BBVA_WHITE,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        )
        self.btn_browse.grid(row=1, column=1, sticky="e")

        # Línea divisoria sutil
        divider = ctk.CTkFrame(control_card, fg_color="#E9EEF2", height=1)
        divider.grid(row=1, column=0, padx=22, sticky="ew")

        # Fila Inferior: Toggle Modo Oculto/Visible + Botón Ejecutar
        actions_section = ctk.CTkFrame(control_card, fg_color="transparent")
        actions_section.grid(row=2, column=0, padx=22, pady=(14, 18), sticky="ew")
        actions_section.grid_columnconfigure(1, weight=1)

        # Contenedor del Toggle
        toggle_container = ctk.CTkFrame(actions_section, fg_color="#F0F5FA", corner_radius=8)
        toggle_container.grid(row=0, column=0, sticky="w", ipadx=10, ipady=6)

        self.switch_headless = ctk.CTkSwitch(
            toggle_container,
            text="Modo Oculto (Headless)",
            variable=self.modo_oculto_var,
            command=self._actualizar_etiqueta_modo,
            onvalue=True,
            offvalue=False,
            progress_color=BBVA_AQUA,
            button_color=BBVA_NAVY,
            button_hover_color=BBVA_MEDIUM_BLUE,
            text_color=BBVA_NAVY,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        )
        self.switch_headless.pack(side="left", padx=(12, 10), pady=4)

        self.lbl_modo_desc = ctk.CTkLabel(
            toggle_container,
            text="[Navegador Visible]",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=BBVA_MEDIUM_BLUE
        )
        self.lbl_modo_desc.pack(side="left", padx=(0, 12))

        # Botones de Acción (Limpiar Consola e Iniciar Carga)
        buttons_right = ctk.CTkFrame(actions_section, fg_color="transparent")
        buttons_right.grid(row=0, column=2, sticky="e")

        self.btn_clear = ctk.CTkButton(
            buttons_right,
            text="Limpiar Consola",
            command=self._limpiar_consola,
            height=40,
            width=130,
            corner_radius=6,
            fg_color="#E4EBF2",
            hover_color="#D0DCE8",
            text_color=BBVA_NAVY,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        )
        self.btn_clear.pack(side="left", padx=(0, 12))

        self.btn_start = ctk.CTkButton(
            buttons_right,
            text="▶  INICIAR CARGA RPA",
            command=self._iniciar_ejecucion_rpa,
            height=40,
            width=210,
            corner_radius=6,
            fg_color=BBVA_MEDIUM_BLUE,
            hover_color=BBVA_NAVY,
            text_color=BBVA_WHITE,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        )
        self.btn_start.pack(side="left")

        # ---------------------------------------------------------
        # 3. CONSOLA DE PROGRESO EN TIEMPO REAL
        # ---------------------------------------------------------
        console_card = ctk.CTkFrame(
            self,
            fg_color=BBVA_NAVY,
            corner_radius=10,
            border_width=1,
            border_color="#12366B"
        )
        console_card.grid(row=2, column=0, padx=24, pady=(0, 20), sticky="nsew")
        console_card.grid_columnconfigure(0, weight=1)
        console_card.grid_rowconfigure(2, weight=1)

        # Cabecera de la Consola
        console_header = ctk.CTkFrame(console_card, fg_color="#051B3B", corner_radius=8, height=38)
        console_header.grid(row=0, column=0, padx=12, pady=(10, 6), sticky="ew")
        console_header.grid_columnconfigure(0, weight=1)

        lbl_console_title = ctk.CTkLabel(
            console_header,
            text="  TERMINAL DE PROGRESO Y AUDITORÍA EN TIEMPO REAL",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=BBVA_AQUA
        )
        lbl_console_title.grid(row=0, column=0, padx=10, pady=6, sticky="w")

        self.lbl_file_indicator = ctk.CTkLabel(
            console_header,
            text=f"Archivo: {Path(self.selected_json_path.get()).name}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#8CA4C4"
        )
        self.lbl_file_indicator.grid(row=0, column=1, padx=14, pady=6, sticky="e")

        # Barra de progreso indeterminada (activa durante la ejecución)
        self.progress_bar = ctk.CTkProgressBar(
            console_card,
            height=4,
            corner_radius=2,
            fg_color="#051B3B",
            progress_color=BBVA_AQUA,
            mode="determinate"
        )
        self.progress_bar.grid(row=1, column=0, padx=14, pady=(0, 6), sticky="ew")
        self.progress_bar.set(0)

        # Cuadro de Texto de Consola
        self.console_textbox = ctk.CTkTextbox(
            console_card,
            fg_color=BBVA_CONSOLE_BG,
            text_color="#E6EDF5",
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=6,
            wrap="word",
            activate_scrollbars=True
        )
        self.console_textbox.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.console_textbox.configure(state="disabled")

        # Configurar etiquetas de color para enriquecer las líneas de consola
        text_widget = self.console_textbox._textbox
        text_widget.tag_config("OK", foreground="#2DCCCD")       # Aqua BBVA
        text_widget.tag_config("INFO", foreground="#5BC0FF")     # Azul Claro
        text_widget.tag_config("WARN", foreground="#F8CD51")     # Amarillo Corporativo BBVA
        text_widget.tag_config("ERROR", foreground="#FF6B6B")    # Coral / Rojo Alerta
        text_widget.tag_config("SECTION", foreground="#2DCCCD", font=("Consolas", 12, "bold"))
        text_widget.tag_config("NORMAL", foreground="#DCE5F0")

    def _actualizar_etiqueta_modo(self):
        """Actualiza el indicador visual del modo Oculto/Visible."""
        if self.modo_oculto_var.get():
            self.lbl_modo_desc.configure(
                text="[Ejecución en 2do Plano]",
                text_color="#008484"
            )
            _info("Modo cambiado a: OCULTO (Headless activado).")
        else:
            self.lbl_modo_desc.configure(
                text="[Navegador Visible]",
                text_color=BBVA_MEDIUM_BLUE
            )
            _info("Modo cambiado a: VISIBLE (Ventana de Chrome visible).")

    def _seleccionar_archivo_json(self):
        """Abre el explorador para elegir el archivo JSON de oficios."""
        if self.is_running:
            return

        ruta = filedialog.askopenfilename(
            title="Seleccionar archivo JSON de Oficios",
            initialdir=str(BASE_DIR),
            filetypes=[("Archivos JSON", "*.json"), ("Todos los archivos", "*.*")]
        )
        if ruta:
            self.selected_json_path.set(ruta)
            nombre = Path(ruta).name
            self.lbl_file_indicator.configure(text=f"Archivo: {nombre}")
            _ok(f"Archivo JSON seleccionado: {ruta}")

    def _limpiar_consola(self):
        """Limpia el contenido de la consola visual."""
        self.console_textbox.configure(state="normal")
        self.console_textbox.delete("1.0", "end")
        self.console_textbox.configure(state="disabled")

    def _insertar_linea_consola(self, raw_text: str):
        """Limpia secuencias ANSI y aplica color semántico en el CTkTextbox."""
        clean_text = self.ANSI_ESCAPE_RE.sub("", raw_text)

        # Determinar etiqueta de color según el contenido de la línea
        tag = "NORMAL"
        if "[OK]" in clean_text:
            tag = "OK"
        elif "[ERROR]" in clean_text or "Error" in clean_text or "falló" in clean_text:
            tag = "ERROR"
        elif "[WARN]" in clean_text:
            tag = "WARN"
        elif "[INFO]" in clean_text:
            tag = "INFO"
        elif "✦" in clean_text or "━" in clean_text or "▸" in clean_text:
            tag = "SECTION"

        self.console_textbox.configure(state="normal")
        self.console_textbox._textbox.insert("end", clean_text, tag)
        self.console_textbox.see("end")
        self.console_textbox.configure(state="disabled")

    def _procesar_cola_logs(self):
        """Escucha continuamente la cola de mensajes para actualizar la consola sin congelar la UI."""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self._insertar_linea_consola(msg)
        except queue.Empty:
            pass
        finally:
            self.after(60, self._procesar_cola_logs)

    def _iniciar_ejecucion_rpa(self):
        """Valida entradas y lanza el proceso RPA en un hilo secundario."""
        if self.is_running:
            return

        ruta_str = self.selected_json_path.get().strip()
        if not ruta_str:
            _error("Por favor selecciona un archivo JSON antes de iniciar.")
            return

        ruta_json = Path(ruta_str)
        if not ruta_json.exists() or not ruta_json.is_file():
            _error(f"El archivo seleccionado no existe: {ruta_json}")
            return

        modo_oculto = self.modo_oculto_var.get()
        self.is_running = True

        # Actualizar estado visual de controles
        self.btn_start.configure(
            state="disabled",
            text="⏳  EJECUTANDO RPA...",
            fg_color="#5A6872"
        )
        self.btn_browse.configure(state="disabled")
        self.switch_headless.configure(state="disabled")
        self.entry_json.configure(state="disabled")

        self.status_badge.configure(
            text="●  PROCESANDO OFICIOS",
            text_color="#F8CD51",
            fg_color="#103A75"
        )
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()

        # Ejecutar proceso asíncrono en un hilo independiente para mantener fluida la GUI
        hilo_rpa = threading.Thread(
            target=self._worker_rpa_thread,
            args=(ruta_json, modo_oculto),
            daemon=True
        )
        hilo_rpa.start()

    def _worker_rpa_thread(self, ruta_json: Path, modo_oculto: bool):
        """Ejecuta el event loop de asyncio en un hilo dedicado."""
        try:
            asyncio.run(ejecutar_rpa_async(ruta_json, modo_oculto))
        except Exception as exc:
            _error(f"Fallo no controlado en el hilo de ejecución: {exc}")
        finally:
            self.after(0, self._finalizar_ejecucion_ui)

    def _finalizar_ejecucion_ui(self):
        """Restaura el estado de los botones al terminar el RPA."""
        self.is_running = False
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(1)

        self.btn_start.configure(
            state="normal",
            text="▶  INICIAR CARGA RPA",
            fg_color=BBVA_MEDIUM_BLUE
        )
        self.btn_browse.configure(state="normal")
        self.switch_headless.configure(state="normal")
        self.entry_json.configure(state="normal")

        self.status_badge.configure(
            text="●  PROCESO FINALIZADO",
            text_color=BBVA_AQUA,
            fg_color="#0D3166"
        )

    def on_closing(self):
        """Restaura los flujos estándar al cerrar la aplicación."""
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        self.destroy()
