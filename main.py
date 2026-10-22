import asyncio
import unicodedata
import os
import pandas as pd
import shutil
from typing import Tuple, Optional
from datetime import datetime
from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError
)
import re
import sys
import json
import ast
from contextlib import contextmanager
import contextvars
import math
import threading
import queue
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk

# =========================================
# URLs de Operación SUGO y Google Drive
# =========================================

URL_SUGO_LOGIN = "https://acprod.intranet.com.mx/mbom_mx_ws/mbom_mx_web/PortalLogon"
URL_SUGO_MAIN = "https://acprod.intranet.com.mx/mbom_mx_ws/mbom_mx_web/mbom_mx_web_jsp/portal3.jsp"
URL_ALTA_OFICIO = "https://acprod.intranet.com.mx/boixp_mx_web/boixp_mx_web/servlet/ServletOperacionWeb?OPERACION=VGOMX002&LOCALE=es_ES&DATOS_ENTRADA.FLUJO_LANZAR=GOMXFL10010"
URL_ALTA_PERSONA = "https://acprod.intranet.com.mx/boixp_mx_web/boixp_mx_web/servlet/ServletOperacionWeb?OPERACION=VGOMX003&LOCALE=es_ES&DATOS_ENTRADA.FLUJO_LANZAR=GOMXFL10021"
URL_FINALIZAR_CAPTURA = "https://acprod.intranet.com.mx/boixp_mx_web/boixp_mx_web/servlet/ServletOperacionWeb?OPERACION=VGOMX005&LOCALE=es_ES&DATOS_ENTRADA.FLUJO_LANZAR=GOMXFL10180"
URL_SUGO = "https://acprod.intranet.com.mx/mbom_mx_ws/mbom_mx_web/mbom_mx_web_jsp/portal3.jsp"
URL_SUGO_ESTATUS = "https://acprod.intranet.com.mx/boixp_mx_web/boixp_mx_web/servlet/ServletOperacionWeb?OPERACION=VGOMX012&LOCALE=es_ES&DATOS_ENTRADA.FLUJO_LANZAR=GOMXFL10090"
URL_GOOGLE_DRIVE = "https://drive.google.com/drive/u/0/"
URL_LOGIN_GOOGLE = "https://accounts.google.com/"

ARGUMENTOS_CHROME = [
    "--ignore-certificate-errors",
    "--disable-blink-features=AutomationControlled",
    "--disable-gpu",
    "--no-sandbox",
    "--no-first-run",             
    "--no-default-browser-check", 
    "--disable-sync",             
    "--disable-popup-blocking",
    "--disable-signin-promo",
    "--disable-features=ChromeSigninInterceptBubble,DiceWebSigninIntercept"
]

# =========================================
# Rutas y Configuración de Archivos
# =========================================

IS_FROZEN = getattr(sys, 'frozen', False)  # Detecta si es ejecutable Exe o Desarrollo

if IS_FROZEN:
    BASE_DIR = Path(sys.executable).parent
    INTERNAL_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent
    INTERNAL_DIR = BASE_DIR

DIST_DIR = BASE_DIR / "dist"
DIR_ARCHIVOS = BASE_DIR / "archivos"
INPUT_FILE = BASE_DIR / "Oficios.xlsx"
INPUT_JSON_FILE = BASE_DIR / "oficios.json"
ARCHIVO_CREDENCIALES = BASE_DIR / "usuario_sugo.json"
USER_DATA_DIR = DIST_DIR / "perfil_google_drive"
ASSETS_DIR = INTERNAL_DIR / "app" / "assets"
TEMP_FILE = DIST_DIR / "resultados_temp.csv"
FILE_EXITOS = DIST_DIR / "resultados_procesados.xlsx"

BATCH_GUARDADO = 10
PROGRESS_STATUS_COLUMN = "Validacion Informe"
PROGRESS_COLUMNS = [
    PROGRESS_STATUS_COLUMN,
    "folio_sugo",
    "fase_proceso",
    "mensaje",
    "fecha_actualizacion",
]
PROGRESS_ID_COLUMN = "id_progreso"
PROGRESS_KEY_COLUMNS = [PROGRESS_ID_COLUMN]

# ================================================
#           Utils y Sistema de Logs
# ================================================

_LOG_INDENT = contextvars.ContextVar("log_indent", default=0)


def normalizar_texto(texto: str) -> str:
    """Elimina tildes y convierte a minúsculas."""
    texto_nfkd = unicodedata.normalize("NFKD", str(texto))
    return (
        "".join([c for c in texto_nfkd if not unicodedata.combining(c)])
        .strip()
        .lower()
    )


def calcular_plazo_dias(plazo: dict, dias_default: int = 3) -> int:
    cantidad = (plazo.get("cantidad", 0) or 0)
    unidad = normalizar_texto(plazo.get("unidad", ""))

    if "hora" in unidad:
        return max(1, math.ceil(cantidad / 24))

    if "dia" in unidad:
        return max(1, int(cantidad))

    return dias_default


@contextmanager
def _log_indent(levels: int = 1):
    token = _LOG_INDENT.set(_LOG_INDENT.get() + levels)
    try:
        yield
    finally:
        _LOG_INDENT.reset(token)


def _log_prefix(extra_indent: int = 0) -> str:
    return "  " * max(_LOG_INDENT.get() + extra_indent, 0)


def _log_line(label: str, color: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    indent = _log_prefix()
    print(f"\033[90m[{ts}]\033[0m {indent}{color}{label}\033[0m {msg}")


def estandarizar_fechas(fecha):
    meses_es = {
        "ene": "01",
        "feb": "02",
        "mar": "03",
        "abr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "ago": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dic": "12",
    }
    fecha = str(fecha).strip().lower()
    if pd.isnull(fecha) or fecha == "nat" or fecha == "":
        return ""
    for mes, num in meses_es.items():
        if mes in fecha:
            fecha = fecha.replace(mes, num)
            break
    formatos = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d-%m-%y",
        "%d-%m-%Y",
        "%d %m %Y",
        "%m/%d/%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%y %H:%M:%S",
    ]
    for formato in formatos:
        try:
            fecha_obj = datetime.strptime(fecha, formato)
            return fecha_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _section(title: str, subtitle: str = None) -> None:
    """Imprime un encabezado de sección resaltado y con color, con subtítulo opcional."""
    ts = datetime.now().strftime("%H:%M:%S")

    CYAN = "\033[96m"
    GRIS = "\033[90m"
    BOLD = "\033[1m"
    ITALIC = "\033[3m"
    RESET = "\033[0m"

    longitud_maxima = len(title)
    if subtitle and len(subtitle) > len(title):
        longitud_maxima = len(subtitle)

    linea = "━" * (longitud_maxima + 15)

    print(f"\n{GRIS}[{ts}]{RESET} {CYAN}{BOLD}✦ {title.upper()} {RESET}")

    if subtitle:
        print(f"             {GRIS}{ITALIC}{subtitle}{RESET}")

    print(f"{CYAN}{linea}{RESET}")


def _subsection(title: str, subtitle: str = None) -> None:
    ts = datetime.now().strftime("%H:%M:%S")

    CYAN = "\033[96m"
    GRIS = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    indent = _log_prefix()
    print(f"\033[90m[{ts}]\033[0m {indent}{CYAN}{BOLD}▸ {title}{RESET}")
    if subtitle:
        print(f"           {indent}{GRIS}{subtitle}{RESET}")


def _ok(msg: str) -> None:
    _log_line("[OK]   ", "\033[92m", msg)


def _info(msg: str) -> None:
    _log_line("[INFO] ", "\033[94m", msg)


def _warn(msg: str) -> None:
    _log_line("[WARN] ", "\033[93m", msg)


def _error(msg: str) -> None:
    _log_line("[ERROR]", "\033[91m", msg)


def _parse_clientes_objetivo(value):
    if isinstance(value, list):
        return value
    if pd.isnull(value):
        return []
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError, SyntaxError):
            try:
                parsed = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return []
        return parsed if isinstance(parsed, list) else []
    return []


def asegurar_ids_progreso(df: pd.DataFrame) -> pd.DataFrame:
    """Asigna un identificador estable por ocurrencia para no mezclar duplicados."""
    if PROGRESS_ID_COLUMN in df.columns:
        return df

    oficio = df.get("oficio_autoridad", pd.Series("", index=df.index)).fillna("").astype(str)
    expediente = df.get("expediente_autoridad", pd.Series("", index=df.index)).fillna("").astype(str)
    llave_base = oficio.str.strip() + "|" + expediente.str.strip()
    df[PROGRESS_ID_COLUMN] = llave_base + "|" + llave_base.groupby(llave_base).cumcount().astype(str)
    return df


def guardar_progreso(df: pd.DataFrame) -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    df_guardado = df.copy()

    if "clientes_objetivo" in df_guardado.columns:
        df_guardado["clientes_objetivo"] = df_guardado["clientes_objetivo"].apply(
            lambda value: json.dumps(_parse_clientes_objetivo(value), ensure_ascii=False)
        )

    df_guardado.to_csv(TEMP_FILE, index=False, encoding="utf-8-sig")


def cargar_oficios(ruta_json: Optional[Path] = None) -> pd.DataFrame:
    """Carga los oficios desde el archivo JSON seleccionado o el archivo por defecto."""
    archivo_entrada = Path(ruta_json) if ruta_json else INPUT_JSON_FILE

    if not archivo_entrada.exists():
        raise FileNotFoundError(f"No se encontró el archivo '{archivo_entrada}'.")

    _info(f"Leyendo archivo de entrada: {archivo_entrada}")
    with open(archivo_entrada, "r", encoding="utf-8") as f:
        registros = json.load(f)

    if not isinstance(registros, list):
        raise ValueError("El archivo JSON debe contener una lista de registros.")

    df = pd.DataFrame(registros)
    asegurar_ids_progreso(df)
    for column in PROGRESS_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    if "clientes_objetivo" not in df.columns:
        df["clientes_objetivo"] = [[] for _ in range(len(df))]
    else:
        df["clientes_objetivo"] = df["clientes_objetivo"].apply(_parse_clientes_objetivo)

    if TEMP_FILE.exists():
        _info(f"Se encontró progreso previo: {TEMP_FILE}")
        df_temp = pd.read_csv(TEMP_FILE, dtype=str, keep_default_na=False)
        asegurar_ids_progreso(df_temp)
        for column in PROGRESS_COLUMNS:
            if column not in df_temp.columns:
                df_temp[column] = ""

        merge_keys = [column for column in PROGRESS_KEY_COLUMNS if column in df.columns and column in df_temp.columns]
        if merge_keys:
            progress = df_temp[merge_keys + PROGRESS_COLUMNS].drop_duplicates(
                subset=merge_keys,
                keep="last",
            )
            df = df.merge(progress, on=merge_keys, how="left", suffixes=("", "_progreso"))

            for column in PROGRESS_COLUMNS:
                progress_column = f"{column}_progreso"
                if progress_column in df.columns:
                    df[column] = df[progress_column].fillna(df[column])
                    df.drop(columns=[progress_column], inplace=True)
            _ok("Progreso previo combinado con los oficios de entrada.")
        else:
            _warn("No se pudo combinar el progreso previo: faltan columnas llave.")

    df[PROGRESS_STATUS_COLUMN] = df[PROGRESS_STATUS_COLUMN].fillna("").astype(str)
    return df


def marcar_progreso(
    df: pd.DataFrame,
    idx,
    status: str,
    mensaje: str = "",
    folio_sugo: str = "",
    fase: Optional[str] = None,
) -> None:
    df.at[idx, PROGRESS_STATUS_COLUMN] = status
    df.at[idx, "mensaje"] = mensaje
    df.at[idx, "fecha_actualizacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if folio_sugo:
        df.at[idx, "folio_sugo"] = folio_sugo
    if fase is not None:
        df.at[idx, "fase_proceso"] = fase
    guardar_progreso(df)
    detalle_folio = f" | Folio SUGO: {folio_sugo}" if folio_sugo else ""
    detalle_mensaje = f" | {mensaje}" if mensaje else ""
    _info(f"Progreso actualizado: {status}{detalle_folio}{detalle_mensaje}")


def limpiar_texto(texto: str) -> str:
    if not texto:
        return ""
    texto = texto.lower()
    texto = "".join([c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"])
    return texto


def cargar_credenciales_sugo() -> Tuple[str, str]:
    """Carga usuario y contraseña del archivo JSON."""
    try:
        with open(ARCHIVO_CREDENCIALES, "r", encoding="utf-8") as f:
            creds = json.load(f)
        return creds["user"], creds["password"]
    except FileNotFoundError:
        msg = f"No se encontró el archivo '{ARCHIVO_CREDENCIALES}'."
        _error(msg)
        raise FileNotFoundError(msg)
    except KeyError as exc:
        msg = f"Formato de credenciales inválido. Falta la clave {exc}."
        _error(msg)
        raise KeyError(msg)
    except Exception as exc:
        msg = f"Error inesperado al cargar credenciales: {exc}"
        _error(msg)
        raise RuntimeError(msg)


async def select_best_option(page: Page, selector: str, value_to_match: str, navigation_expected: bool = False):
    """
    Selecciona una opción basada en normalización de texto y coincidencia parcial.
    """
    def normalize_text(text: str) -> str:
        if not text:
            return ""
        text = "".join(c for c in unicodedata.normalize('NFD', text) 
                    if unicodedata.category(c) != 'Mn')
        text = re.sub(r'\s+', ' ', text)
        return text.lower().strip()
    
    opciones = await page.evaluate(f"""
        Array.from(document.querySelectorAll('{selector} option'))
            .map(o => o.label)
            .filter(label => label.trim() !== "")
    """)

    if not opciones:
        raise ValueError(f"No se encontraron opciones para el selector '{selector}'")

    search_value_norm = normalize_text(value_to_match)
    
    coincidencias_exactas = [
        opcion for opcion in opciones if normalize_text(opcion) == search_value_norm
    ]
    coincidencias_parciales = [
        opcion
        for opcion in opciones
        if search_value_norm in normalize_text(opcion)
        or normalize_text(opcion) in search_value_norm
    ]

    if len(coincidencias_exactas) == 1:
        etiqueta = coincidencias_exactas[0]
    elif len(coincidencias_parciales) == 1:
        etiqueta = coincidencias_parciales[0]
    elif len(coincidencias_parciales) > 1:
        raise ValueError(
            f"Coincidencia ambigua para '{value_to_match}' en '{selector}': "
            f"{coincidencias_parciales[:5]}"
        )
    else:
        raise ValueError(
            f"No existe una coincidencia exacta o única para '{value_to_match}' en '{selector}'."
        )

    _ok(f"Selector {selector}: '{value_to_match}' -> '{etiqueta}'")

    try:
        if navigation_expected:
            async with page.expect_navigation():
                await page.select_option(selector, label=etiqueta)
        else:
            await page.select_option(selector, label=etiqueta)
        return etiqueta
    except Exception as e:
        raise ValueError(f"Error al seleccionar '{etiqueta}' '{selector}': {e}")


# =========================================
# Funciones de ejecución de procesos
# =========================================

async def registro_alta_oficio(
    page: Page,
    *,
    oficio_autoridad: str,
    expediente_autoridad: str,
    origen_folio: str,
    region: str,
    plaza: str,
    tipo_oficio: str,
    autoridad_especifica: str,
    autoridad: str,
    subautoridad: str,
    oficio_subautoridad: str,
    expediente_subautoridad: str,
    fecha_recepcion: str,
    plazo_dias: int,
    abogado_solicitante: str,
    empresa: str,
    file_name: Path
):
    try:
        _subsection("Alta de oficio", oficio_autoridad)
        with _log_indent():
            _info("Abriendo formulario de alta de oficio.")
            await page.goto(URL_ALTA_OFICIO, wait_until="domcontentloaded", timeout=60000)

            _info("Seleccionando origen de folio, región, plaza y tipo de oficio.")
            with _log_indent():
                await select_best_option(
                    page=page,
                    selector="select#listOF", 
                    value_to_match=origen_folio, 
                    navigation_expected=True
                )

                await select_best_option(
                    page=page,
                    selector="select#listRegion", 
                    value_to_match=region, 
                    navigation_expected=True
                )

                await select_best_option(
                    page=page,
                    selector="select#listPlaza", 
                    value_to_match=plaza, 
                    navigation_expected=True
                )

                await select_best_option(
                    page=page,
                    selector="#listOficio", 
                    value_to_match=tipo_oficio, 
                    navigation_expected=False
                )

            if autoridad_especifica:
                _info(f"Buscando autoridad específica: {autoridad_especifica}")
                with _log_indent():
                    async with page.context.expect_page() as page_autoridades:
                        await page.evaluate(""" () => AutoE(); """)

                    page_select_autoridad = await page_autoridades.value
                    await page_select_autoridad.wait_for_load_state()

                    pagination = True

                    while pagination:
                        td_autoridad_seleccionada = page_select_autoridad.locator("td").filter(
                            has_text=autoridad_especifica
                        ).first

                        if await td_autoridad_seleccionada.count() > 0:
                            checkbox = td_autoridad_seleccionada.locator(
                                "input[type='radio']"
                            ).first
                            
                            await checkbox.check()
                            await asyncio.sleep(0.5)
                            await page_select_autoridad.evaluate(""" () => enviaDatos(); """)
                            _ok("Autoridad específica seleccionada.")
                            break
                        else:
                            btn_siguiente = page_select_autoridad.locator("#Btn_Siguiente_on")
                            if await btn_siguiente.count() and await btn_siguiente.is_enabled():
                                await btn_siguiente.click()
                                await page_select_autoridad.wait_for_timeout(1000)
                            else:
                                pagination = False
                    else:
                        _warn(f"'{autoridad_especifica}' no existe en Autoridad Específica.")
                        await page_select_autoridad.close()

            _info("Seleccionando autoridad, abogado y empresa.")
            with _log_indent():
                await select_best_option(
                    page=page,
                    selector="select#listAutoridad", 
                    value_to_match=autoridad
                )

            _info("Capturando datos del oficio.")
            with _log_indent():
                await page.fill("#ofiCNBV", oficio_autoridad)
                await page.fill("#expediente", expediente_autoridad)
                await page.fill("#subAutoridad", subautoridad)
                await page.fill("#ofiSUB", oficio_subautoridad)
                await page.fill("#expedienteSub", expediente_subautoridad)
                await page.evaluate(
                    f"document.getElementById('fechaFin').value = '{fecha_recepcion}'"
                )
                await page.fill("#plazo", str(plazo_dias))

                if origen_folio != "VENTANILLA":
                    await select_best_option(
                        page=page,
                        selector="select#cbAbogado", 
                        value_to_match=abogado_solicitante
                    )

                await select_best_option(
                    page=page,
                    selector="select#cbEmpresa", 
                    value_to_match=empresa
                )

            loop = asyncio.get_running_loop()
            resultado_alerta = loop.create_future()

            async def aceptar_alerta(dialog):
                mensaje = dialog.message.strip()
                await dialog.accept()
                if not resultado_alerta.done():
                    resultado_alerta.set_result(mensaje)

            page.once("dialog", aceptar_alerta)
            _info("Guardando alta de oficio.")
            await page.evaluate("guardar()")

            try:
                mensaje_alerta = await asyncio.wait_for(
                    resultado_alerta,
                    timeout=10,
                )
                mensaje_alerta = mensaje_alerta.replace("\n", " ").strip()
            except asyncio.TimeoutError:
                return {
                    "status": "error",
                    "message": "No apareció la alerta después de guardar",
                    "folio_sugo": "",
                }

            if "OFICIO REGISTRADO" not in mensaje_alerta.upper():
                _error(f"SUGO respondió al guardar oficio: {mensaje_alerta}")
                return {
                    "status": "error",
                    "message": mensaje_alerta,
                    "folio_sugo": "",
                }

            elemento_folio = page.locator("#folioSolicitud")
            await elemento_folio.wait_for(state="visible", timeout=15000)

            await page.wait_for_function(
                "() => document.getElementById('folioSolicitud').value.trim() !== ''",
                timeout=15000,
            )

            folio_sugo = await elemento_folio.input_value()
            folio_sugo = str(folio_sugo).strip()

            _ok(f"Oficio registrado en SUGO con folio {folio_sugo}.")

        return {
            "status": "ok",
            "message": "Alta de oficio realizado correctamente",
            "folio_sugo": folio_sugo
        }

    except Exception as e:
        _error(f"Alta de oficio falló: {e}")
        return {
            "status": "error",
            "message": f"Ocurrio un error inesperado: {e}",
            "folio_sugo": ""
        }


async def registro_alta_persona(
    page: Page,
    *,
    folio_sugo: str,
    instrucciones_oficio: str,
    tipo_operacion: str,
    clientes_objetivo: list[dict]
):
    try:
        _subsection("Instrucciones y personas", f"Folio SUGO: {folio_sugo}")
        with _log_indent():
            _info("Abriendo formulario de alta de personas.")
            await page.goto(URL_ALTA_PERSONA, wait_until="domcontentloaded", timeout=60000)

            _info("Buscando oficio por folio SUGO.")
            checkbox = page.locator("#porFolio")
            await checkbox.wait_for(state="visible")
            await checkbox.click()
            await page.fill("#noFolio", folio_sugo)
            await page.evaluate("""() => buscar();""")

            await page.locator("#tablaResultados").wait_for(state="visible", timeout=4000)
            fila_folio = page.locator("#tablaResultados tr").filter(has_text=folio_sugo).first

            if await fila_folio.count() > 0:
                radio_btn = fila_folio.locator("input[type='radio']").first
                async with page.expect_navigation():
                    await radio_btn.check()
                _ok("Oficio localizado y seleccionado.")
            else:
                _error(f"El folio '{folio_sugo}' no se encontró en la tabla.")
                return {
                    "status": "error",
                    "message": f"El folio '{folio_sugo}' no se encontró en la tabla.",
                }

            _info("Capturando instrucciones del oficio.")
            await page.locator("#Observaciones").press_sequentially(instrucciones_oficio)
            await asyncio.sleep(1)
            await page.locator("#btnGuardar").wait_for(state="visible")
            await page.locator("#btnGuardar").click()
            _ok("Instrucciones guardadas.")

            if not clientes_objetivo:
                _info("Lista de clientes objetivo vacía. Agregando registro por defecto (No detectado).")
                clientes_objetivo = [{
                    "tipo_persona": "moral",
                    "nombre": "No detectado"
                }]

            _info(f"Clientes objetivo a procesar: {len(clientes_objetivo)}")
            
            algun_registro_insertado = False

            for numero_cliente, cliente in enumerate(clientes_objetivo, start=1):
                tipo_persona        = str(cliente.get("tipo_persona") or "").strip().lower()
                nombre_cliente      = str(cliente.get("nombre") or "").strip()
                rfc                 = str(cliente.get("rfc") or "").strip()
                cuentas_especificas = cliente.get("cuentas_especificas") or []
                etiqueta_cliente    = nombre_cliente or rfc or "cliente sin nombre"

                _subsection(f"Cliente {numero_cliente}/{len(clientes_objetivo)}", etiqueta_cliente)
                
                with _log_indent():
                    # --- BLOQUE A: Captura por Nombre ---
                    if nombre_cliente:
                        try:
                            if tipo_persona == "moral":
                                _info("Capturando persona moral.")
                                await asyncio.sleep(0.5)
                                await page.locator("#moralR").click()
                                await asyncio.sleep(0.5)
                                await page.locator("#razonS").fill("")
                                await page.locator("#razonS").press_sequentially(nombre_cliente)

                            elif tipo_persona == "fisica":
                                _info("Capturando persona física.")
                                await asyncio.sleep(0.5)
                                await page.locator("#fisicaR").click()

                                partes = nombre_cliente.strip().split()
                                cantidad = len(partes)

                                if cantidad == 4:
                                    nombre = f"{partes[0]} {partes[1]}"
                                    apellido_paterno = partes[2]
                                    apellido_materno = partes[3]
                                elif cantidad >= 3:
                                    apellido_materno = partes[-1]
                                    apellido_paterno = partes[-2]
                                    nombre = " ".join(partes[:-2])
                                elif cantidad == 2:
                                    nombre = partes[0]
                                    apellido_paterno = partes[1]
                                    apellido_materno = ""
                                else:
                                    nombre = partes[0] if partes else ""
                                    apellido_paterno = ""
                                    apellido_materno = ""

                                await asyncio.sleep(0.5)
                                await page.locator("#nombreC").fill("")
                                await page.locator("#nombreC").press_sequentially(nombre)
                                await asyncio.sleep(0.5)
                                await page.locator("#paternoC").fill("")
                                await page.locator("#paternoC").press_sequentially(apellido_paterno)
                                await asyncio.sleep(0.5)
                                await page.locator("#maternoC").fill("")
                                await page.locator("#maternoC").press_sequentially(apellido_materno)

                            else:
                                raise ValueError(f"Tipo de persona inválido: '{tipo_persona}'")

                            if rfc:
                                await asyncio.sleep(0.5)
                                await page.locator("#rfc").fill("")
                                await page.locator("#rfc").press_sequentially(rfc)

                            await asyncio.sleep(0.5)

                            async with page.expect_navigation(timeout=10000):
                                await page.evaluate("anadePer()")

                            _ok(f"Cliente agregado: {etiqueta_cliente}")
                            algun_registro_insertado = True
                            await asyncio.sleep(0.5)

                        except Exception as e:
                            _warn(f"Error al insertar manualmente a '{etiqueta_cliente}': {e}. Continuando flujo...")

                    # --- BLOQUE B: Captura por Cuentas Específicas ---
                    if cuentas_especificas:
                        _info(f"Cuentas específicas a consultar: {len(cuentas_especificas)}")

                        metodos_busqueda = [
                            ("cuenta", "#radioCuenta", "#consultaC"),
                            ("tarjeta", "#radioTarjeta", "#consultaTar"),
                            ("contrato", "#radioContrato", "#consultaCon"),
                        ]

                        for cuenta_original in cuentas_especificas:
                            cuenta = str(cuenta_original or "").strip()
                            if not cuenta:
                                continue

                            localizado = False

                            for nombre_metodo, selector_radio, selector_input in metodos_busqueda:
                                _info(f"Consultando por {nombre_metodo}: {cuenta}")

                                try:
                                    checkbox = page.locator(selector_radio)
                                    await checkbox.wait_for(state="visible")
                                    await checkbox.click()
                                    await asyncio.sleep(0.5)
                                    
                                    campo_input = page.locator(selector_input)
                                    await campo_input.fill("")
                                    await campo_input.press_sequentially(cuenta)

                                    # 1ra navegación: Búsqueda con noMenor()
                                    async with page.expect_navigation(timeout=10000):
                                        await page.evaluate("() => noMenor();")

                                    # Verificar si el sistema pobló los campos tras la búsqueda
                                    await page.wait_for_function(
                                        "() => document.getElementById('razonS')?.value.trim() !== '' || document.getElementById('nombreC')?.value.trim() !== ''",
                                        timeout=5000,
                                    )

                                    # 2da navegación: Agregar persona con anadePer()
                                    async with page.expect_navigation(timeout=10000):
                                        await page.evaluate("() => anadePer();")

                                    _ok(f"Registro agregado exitosamente como {nombre_metodo}: {cuenta}")
                                    localizado = True
                                    algun_registro_insertado = True
                                    break

                                except Exception:
                                    texto_error_sistema = "No se detectó el mensaje de éxito (Timeout)"
                                    try:
                                        await page.wait_for_selector("#BTACEPTAR", timeout=5000)
                                        texto_error_sistema = await page.locator(".TextoAlerta .txtAlertArqVN").inner_text()
                                        
                                        async with page.expect_navigation(timeout=10000):
                                            await page.click("#BTACEPTAR")
                                    except Exception:
                                        pass
                                    finally:
                                        _warn(f"Sin éxito en {nombre_metodo} para {cuenta} ({texto_error_sistema}). Probando siguiente opción...")

                            if not localizado:
                                _warn(f"No se pudo localizar '{cuenta}' en ninguno de los 3 métodos.")

                            await asyncio.sleep(2)

            # VALIDACIÓN FINAL (RESPALDO)
            if not algun_registro_insertado:
                _warn("Ningún cliente o cuenta pudo ser insertado. Capturando 'No detectado' en Persona Moral por defecto.")
                try:
                    await asyncio.sleep(0.5)
                    await page.locator("#moralR").click()
                    await asyncio.sleep(0.5)
                    await page.locator("#razonS").fill("")
                    await page.locator("#razonS").press_sequentially("No detectado")
                    await asyncio.sleep(0.5)

                    async with page.expect_navigation(timeout=10000):
                        await page.evaluate("anadePer()")

                    _ok("Registro por defecto ('No detectado') agregado exitosamente.")
                except Exception as e:
                    return {
                        "status": "error",
                        "message": f"Fallo crítico: No se pudo insertar el cliente por defecto ('No detectado'): {e}"
                    }

            tipo_operacion_limpio = limpiar_texto(tipo_operacion)
            _info("Seleccionando tipo de operación.")

            if "informe" in tipo_operacion_limpio and "juridico" in tipo_operacion_limpio:
                _info("Tipo de operación detectado: informe jurídico.")
                await page.locator("#chJuridico").click()
            elif "aseg" in tipo_operacion_limpio and "insumos" in tipo_operacion_limpio:
                _info("Tipo de operacion detectado: Aseguramientos con insumos")
                await page.locator("#chAseguramiento").click()
                await page.locator("#chAnalisis").click()
            elif "informe" in tipo_operacion_limpio:
                _info("Tipo de operación detectado: informe de insumos.")
                await page.locator("#chAnalisis").click()
            elif "insumos" in tipo_operacion_limpio:
                _info("Tipo de operación detectado: insumos.")
                await page.locator("#chAnalisis").click()
            elif "aseg" in tipo_operacion_limpio:
                _info("Tipo de operacion detectado: Aseguramientos")
                await page.locator("#chAseguramiento").click()
            else:
                _warn(f"No se detectó checkbox para el tipo de operación '{tipo_operacion}'.")

            await asyncio.sleep(0.5)

            dialog_handled = asyncio.Event()
            mensaje_dialogo = ""

            async def handle_dialog(dialog):
                nonlocal mensaje_dialogo
                mensaje_dialogo = dialog.message.strip()
                await dialog.accept()
                dialog_handled.set()

            page.once("dialog", handle_dialog)

            _info("Guardando alta de personas.")
            await page.locator("#btnGuardar2").click()

            intentos = 0
            max_intentos = 15
            error_encontrado = False
            texto_error_sistema = "No se detectó el mensaje de éxito (Timeout)"

            while intentos < max_intentos:
                if dialog_handled.is_set():
                    break

                if await page.is_visible(".TextoAlerta .txtAlertArqVN") and not error_encontrado:
                    error_encontrado = True
                    texto_error_sistema = await page.locator(".TextoAlerta .txtAlertArqVN").inner_text()
                    _warn(f"Aviso del sistema detectado: {texto_error_sistema}")
                    
                    try:
                        await page.wait_for_selector("#BTACEPTAR", timeout=5000)
                        await page.click("#BTACEPTAR")
                    except Exception as e:
                        _warn(f"No se pudo clickear BTACEPTAR: {e}")
                
                await asyncio.sleep(1)
                intentos += 1

            if error_encontrado:
                _error(f"Error al capturar clientes: {texto_error_sistema}")
                return {
                    "status": "error",
                    "message": f"Error al capturar cliente: {texto_error_sistema}" 
                }

            if dialog_handled.is_set():
                dialogo_normalizado = normalizar_texto(mensaje_dialogo)
                if any(texto in dialogo_normalizado for texto in ("error", "incorrect", "fall", "no se pudo")):
                    return {
                        "status": "error",
                        "message": f"SUGO rechazó el alta de personas: {mensaje_dialogo}",
                    }
                _ok(f"Alerta aceptada correctamente: {mensaje_dialogo}")
            else:
                return {
                    "status": "error",
                    "message": "No se confirmó el guardado del alta de personas.",
                }

        return {
            "status": "ok",
            "message": "Alta de personas realizada correctamente",
        }
        
    except Exception as e:
        _error(f"Alta de personas falló: {e}")
        return {
            "status": "error",
            "message": f"Ocurrió un error inesperado en alta de personas: {e}",
        }


async def registro_finalizar_captura(page: Page, folio_sugo):
    try:
        _subsection("Finalización", f"Folio SUGO: {folio_sugo}")
        with _log_indent():
            _info("Abriendo formulario de finalización.")
            await page.goto(URL_FINALIZAR_CAPTURA, wait_until="domcontentloaded", timeout=60000)

            _info("Buscando oficio para finalizar captura.")
            checkbox = page.locator("#porFolio")
            await checkbox.wait_for(state="visible")
            await checkbox.click()
            await page.fill("#noFolio", folio_sugo)

            async with page.expect_navigation():
                await page.evaluate("buscar()")

            checkbox_folio = page.locator("#checks0")
            await checkbox_folio.wait_for(state="visible")
            await checkbox_folio.click()
            _ok("Oficio seleccionado para finalizar.")

            await asyncio.sleep(0.5)

            loop = asyncio.get_running_loop()
            resultado_alerta = loop.create_future()

            async def aceptar_alerta(dialog):
                mensaje = dialog.message.strip()
                await dialog.accept()
                if not resultado_alerta.done():
                    resultado_alerta.set_result(mensaje)

            page.once("dialog", aceptar_alerta)

            _info("Enviando finalización de captura.")
            await page.locator("#btnFinCaptura").click()
            try:
                mensaje_alerta = await asyncio.wait_for(resultado_alerta, timeout=10)
            except asyncio.TimeoutError:
                return {
                    "status": "error",
                    "message": "No se confirmó la finalización de captura.",
                }

            alerta_normalizada = normalizar_texto(mensaje_alerta)
            if any(texto in alerta_normalizada for texto in ("error", "incorrect", "fall", "no se pudo")):
                return {
                    "status": "error",
                    "message": f"SUGO rechazó la finalización: {mensaje_alerta}",
                }
            _ok(f"Alerta aceptada correctamente: {mensaje_alerta}")

        return {
            "status": "ok",
            "message": "Captura finalizada correctamente",
        }
    except Exception as e:
        _error(f"Finalización de captura falló: {e}")
        return {
            "status": "error",
            "message": f"Ocurrio un error inesperado al finalizar captura: {e}",
        }


async def cargar_oficio_sugo(
        page: Page,
        *,
        folio_sugo: str,
        archivo_oficio: str,
): 
    _subsection("Carga Oficio", f"Folio SUGO: {folio_sugo}")
    
    if not folio_sugo:
        return {
            "status": "error",
            "message": "Falta el Folio Sugo."
        }

    file_oficio = Path(archivo_oficio)
    
    if not file_oficio.exists() or not file_oficio.is_file():
        return {
            "status": "error",
            "message": "No se encontro el archivo"
        }

    try:
        page_repositorio = None
        pagina_upload = None

        await page.goto(URL_SUGO_ESTATUS, wait_until="domcontentloaded", timeout=6_000)

        checkbox = page.locator("#rSugo")
        await checkbox.wait_for(state="visible")
        await checkbox.click()

        await page.fill("#fSugo", folio_sugo)

        async with page.expect_navigation():
            await page.evaluate("buscar();")

        await page.wait_for_selector("#tablaResultados", timeout=3000)

        checkbox_folio = page.locator("input[name='Tipo'][type='radio']")
        await checkbox_folio.wait_for(state="visible")
        await checkbox_folio.click()

        try:
            await page.locator("#btnIMAX").click()

            intentos = 0
            max_intentos = 10

            while intentos < max_intentos:
                for p in page.context.pages:
                    if not p.is_closed():
                        if p != page and not p.is_closed():
                            if "image-viewer.jsp" in p.url:
                                page_repositorio = p
                                break

                if page_repositorio:
                    break
                    
                await asyncio.sleep(0.5)
                intentos += 1

            if not page_repositorio:
                return {
                    "status": "error",
                    "message": "No se pudo abrir el repositiorio de SUGO verifica la VPN"
                }

            await page_repositorio.wait_for_load_state("domcontentloaded")
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error inesperado al abrir el repositorio de SUGO: {str(e)}"
            }
            
        frame_visor = page_repositorio.frame_locator('frame[name="viewerFrame"]')
        link_upload = frame_visor.locator('a[href="javascript:imageManager(2)"]')

        async with page_repositorio.context.expect_page() as upload_popup_info:
            await link_upload.click()

        pagina_upload = await upload_popup_info.value
        await pagina_upload.wait_for_load_state("domcontentloaded")

        input_file0 = pagina_upload.locator("#file0")
        await input_file0.set_input_files(file_oficio)

        await pagina_upload.click("//input[@type='submit']")

        try:
            await pagina_upload.wait_for_event("close", timeout=90_000)
        except Exception:
            if not pagina_upload.is_closed():
                await pagina_upload.close()

        return {
            "status": "ok",
            "message": "Se cargo exitosamente el oficio en SUGO."
        }

    except PlaywrightTimeoutError:
        texto_error_sistema = "No se detectó el mensaje de éxito (Timeout)"

        try:
            await page.wait_for_selector("#BTACEPTAR", timeout=15000)
            texto_error_sistema = await page.locator(
                ".TextoAlerta .txtAlertArqVN"
            ).inner_text()

            async with page.expect_navigation():
                await page.click("#BTACEPTAR")

        except Exception:
            await page.goto(URL_SUGO_ESTATUS, wait_until="domcontentloaded")

        return {
            "status": "error",
            "message": texto_error_sistema
        }

    except Exception:
        await page.goto(URL_SUGO_ESTATUS, wait_until="domcontentloaded")
        return {
            "status": "error",
            "message": "Ocurrio un error inesperado en el portal de SUGO."
        }

    finally:
        if pagina_upload:
            try:
                if not pagina_upload.is_closed():
                    await pagina_upload.close()
            except Exception:
                pass

        if page_repositorio:
            try:
                if not page_repositorio.is_closed():
                    await page_repositorio.close()
            except Exception:
                pass

        await page.bring_to_front()


async def descargar_archivo(
    page_drive: Page,
    url_archivo: str,
    carpeta_destino: str = "."
):
    detectar_descarga = None
    detectar_pestana = None
    contexto = None
    paginas_temporales = []
    try:
        os.makedirs(carpeta_destino, exist_ok=True)

        await page_drive.goto(url_archivo, wait_until="domcontentloaded", timeout=80_000)

        selector_descarga = (
            'button[aria-label="Descargar"], '
            'div[aria-label="Descargar"], '
            'button[aria-label="Download"], '
            'div[aria-label="Download"]'
        )

        boton = page_drive.locator(selector_descarga).first
        await boton.wait_for(state="visible", timeout=80_000)

        loop = asyncio.get_running_loop()
        descarga_futura = loop.create_future()

        def detectar_descarga(download):
            if not descarga_futura.done():
                descarga_futura.set_result(download)

        def detectar_pestana(nueva_pagina):
            paginas_temporales.append(nueva_pagina)
            nueva_pagina.on("download", detectar_descarga)

        contexto = page_drive.context

        page_drive.on("download", detectar_descarga)
        contexto.on("page", detectar_pestana)

        await boton.click(timeout=20_000)

        download = await asyncio.wait_for(descarga_futura, timeout=80)
        nombre_original = download.suggested_filename
        ruta_completa = os.path.join(carpeta_destino, nombre_original)

        await download.save_as(ruta_completa)

        return {
            "status": "ok",
            "message": "Se cargo exitosamente el oficio en SUGO.",
            "ruta": ruta_completa
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Ocurrió un error al descargar: {e}",
            "ruta": ""
        }

    finally:
        if detectar_descarga:
            page_drive.remove_listener("download", detectar_descarga)

        if contexto and detectar_pestana:
            contexto.remove_listener("page", detectar_pestana)

        for pagina in paginas_temporales:
            if detectar_descarga:
                pagina.remove_listener("download", detectar_descarga)


# ================================================
# Browser
# ================================================

async def load_page_sugo(context: BrowserContext, user: str, password: str) -> Optional[Page]:
    page_sugo = await context.new_page()

    try:
        _info("Validando sesión existente de SUGO.")
        async with context.expect_page(timeout=5_000) as page_info:
            await page_sugo.goto(URL_SUGO_LOGIN, timeout=60_000)

        popup = await page_info.value
        await popup.wait_for_load_state()
        await popup.close()

        await page_sugo.bring_to_front()
        await page_sugo.goto(URL_SUGO, timeout=60_000)
        await page_sugo.wait_for_load_state("domcontentloaded")
        _ok("Sesión existente de SUGO disponible.")

    except Exception:
        _info("No se detectó sesión activa. Iniciando sesión con credenciales.")
        await asyncio.sleep(2)
        await page_sugo.fill(".name", user)
        await page_sugo.fill(".pass", password)
        await asyncio.sleep(1)

        try:
            async with context.expect_page(timeout=60_000) as page_info:
                if await page_sugo.locator(
                    "//p[@onclick='validaCampos()']"
                ).is_visible():
                    await page_sugo.evaluate("validaCampos()")

            popup = await page_info.value
            await popup.wait_for_load_state()
            await popup.close()

            await page_sugo.bring_to_front()
            await page_sugo.goto(URL_SUGO, timeout=60_000)
            await page_sugo.wait_for_load_state("domcontentloaded")
            _ok("Login en SUGO completado.")

        except Exception:
            _error("No fue posible iniciar sesión en SUGO.")
            return None

    return page_sugo


async def load_page_drive(context: BrowserContext, p: Playwright, headless: bool):
    page_drive = await context.new_page()

    await page_drive.goto(URL_GOOGLE_DRIVE, timeout=30_000)
    await page_drive.wait_for_load_state(state="domcontentloaded")

    if ('idp/profile' in page_drive.url) or ('accounts.google' in page_drive.url) or ('workspace.google' in page_drive.url):
        await context.close()

        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            channel="chrome",
            args=ARGUMENTOS_CHROME
        )
        page_login = context.pages[0] if context.pages else await context.new_page()

        await page_login.goto(URL_LOGIN_GOOGLE, timeout=10_000)
        await page_login.wait_for_load_state(state="domcontentloaded")

        await page_login.wait_for_url(re.compile(r"myaccount"), timeout=0)
        
        await context.close()

        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=headless,
            channel="chrome",
            args=ARGUMENTOS_CHROME
        )
        page_drive = context.pages[0] if context.pages else await context.new_page()
        
        await page_drive.goto(URL_GOOGLE_DRIVE, timeout=10_000)
        await page_drive.wait_for_load_state(state="domcontentloaded")

    if not 'home' in page_drive.url:
        return context, None

    return context, page_drive


# =========================================
# Orchestrator
# =========================================

async def procesar_oficio(
    df: pd.DataFrame,
    idx,
    row: pd.Series,
    numero: int,
    total: int,
    page_sugo: Page,
    page_drive: Page,
) -> None:
    """Procesa un oficio y persiste cada fase para permitir una reanudación segura."""
    data_oficio = row.to_dict()

    oficio_autoridad            = str(data_oficio.get("oficio_autoridad") or "").strip()
    expediente_autoridad        = str(data_oficio.get("expediente_autoridad") or "").strip()
    instrucciones_oficio        = str(data_oficio.get("instrucciones_oficio") or "").strip() + "____INSTRUCCIONES_GENERADAS_POR_EL_BOT_DE_REGISTRO"
    origen_folio                = str(data_oficio.get("origen_folio") or "").strip()
    tipo_oficio                 = str(data_oficio.get("tipo_oficio") or "").strip()
    autoridad_especifica        = str(data_oficio.get("autoridad_especifica") or "").strip()
    region                      = str(data_oficio.get("region") or "").strip()
    plaza                       = str(data_oficio.get("plaza") or "").strip()
    autoridad                   = str(data_oficio.get("autoridad") or "").strip()
    subautoridad_abreviada      = str(data_oficio.get("subautoridad_abreviada") or "").strip()
    oficio_subautoridad         = str(data_oficio.get("oficio_subautoridad") or "").strip()
    expediente_subautoridad     = str(data_oficio.get("expediente_subautoridad") or "").strip()
    fecha_recepcion_original    = str(data_oficio.get("fecha_recepcion") or "").strip()
    abogado_solicitante         = str(data_oficio.get("abogado_solicitante") or "").strip().upper()
    empresa                     = str(data_oficio.get("empresa") or "").strip()
    tipo_operacion              = str(data_oficio.get("tipo_operacion") or "").strip()
    file_name                   = str(data_oficio.get("name_file") or data_oficio.get("nombre_archivo") or "").strip()
    file_url                    = str(data_oficio.get("url_archivo") or "").strip()
    clientes_objetivo           = data_oficio.get("clientes_objetivo") or []
    plazo                       = data_oficio.get("plazo") or {}
    fase                        = str(data_oficio.get("fase_proceso") or "").strip().lower()
    folio_sugo                  = str(data_oficio.get("folio_sugo") or "").strip()

    _section(
        f"Oficio {numero}/{total}",
        f"{oficio_autoridad} | Expediente: {expediente_autoridad}",
    )
    _LOG_INDENT.set(1)
    _info(f"Origen: {origen_folio} | Tipo: {tipo_oficio}")

    fecha_recepcion = estandarizar_fechas(fecha_recepcion_original)
    if not fecha_recepcion:
        _warn("Fecha de recepción vacía o inválida. Se usará la fecha actual.")
        fecha_recepcion = datetime.now().strftime("%Y-%m-%d")
    fecha_recepcion = datetime.strptime(fecha_recepcion, "%Y-%m-%d").strftime("%d/%m/%Y")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if not oficio_autoridad:
        oficio_autoridad = f"S/N-{timestamp}"
    if not expediente_autoridad:
        expediente_autoridad = f"S/N-{timestamp}"
    plazo_dias = calcular_plazo_dias(plazo)

    if fase == "archivo_cargado":
        marcar_progreso(df, idx, "ok", "Oficio ya cargado en SUGO.", folio_sugo, fase)
        return

    if not folio_sugo:
        marcar_progreso(df, idx, "procesando", "Iniciando alta de oficio", fase="pendiente")
        await page_sugo.bring_to_front()
        results_alta = await registro_alta_oficio(
            page=page_sugo,
            oficio_autoridad=oficio_autoridad,
            expediente_autoridad=expediente_autoridad,
            origen_folio=origen_folio,
            region=region,
            plaza=plaza,
            tipo_oficio=tipo_oficio,
            autoridad_especifica=autoridad_especifica,
            autoridad=autoridad,
            subautoridad=subautoridad_abreviada,
            oficio_subautoridad=oficio_subautoridad,
            expediente_subautoridad=expediente_subautoridad,
            fecha_recepcion=fecha_recepcion,
            plazo_dias=plazo_dias,
            abogado_solicitante=abogado_solicitante,
            empresa=empresa,
            file_name=file_name,
        )
        if results_alta.get("status") != "ok":
            mensaje = results_alta.get("message", "Error en alta de oficio")
            _error(mensaje)
            marcar_progreso(df, idx, "error", mensaje, fase="pendiente")
            return

        folio_sugo = results_alta["folio_sugo"]
        fase = "oficio_alta"
        marcar_progreso(df, idx, "procesando", results_alta.get("message", ""), folio_sugo, fase)
    elif not fase:
        fase = "oficio_alta"
        _warn(f"Se reanudará el folio existente {folio_sugo} desde alta de personas.")
        marcar_progreso(df, idx, "procesando", "Reanudando folio existente.", folio_sugo, fase)

    if fase not in {"personas_alta", "captura_finalizada"}:
        results_clientes = await registro_alta_persona(
            page=page_sugo,
            folio_sugo=folio_sugo,
            instrucciones_oficio=instrucciones_oficio,
            tipo_operacion=tipo_operacion,
            clientes_objetivo=clientes_objetivo,
        )
        if results_clientes.get("status") != "ok":
            mensaje = results_clientes.get("message", "Error en alta de personas")
            _error(mensaje)
            marcar_progreso(df, idx, "error", mensaje, folio_sugo, fase)
            return

        fase = "personas_alta"
        marcar_progreso(df, idx, "procesando", results_clientes.get("message", ""), folio_sugo, fase)

    if fase != "captura_finalizada":
        results_finalizacion = await registro_finalizar_captura(page=page_sugo, folio_sugo=folio_sugo)
        if results_finalizacion.get("status") != "ok":
            mensaje = results_finalizacion.get("message", "Error al finalizar captura")
            _error(mensaje)
            marcar_progreso(df, idx, "error", mensaje, folio_sugo, fase)
            return

        fase = "captura_finalizada"
        marcar_progreso(df, idx, "procesando", results_finalizacion.get("message", ""), folio_sugo, fase)

    await page_drive.bring_to_front()
    results_descarga_archivo = await descargar_archivo(page_drive, file_url, DIR_ARCHIVOS)
    if results_descarga_archivo.get("status") != "ok":
        mensaje = results_descarga_archivo.get("message", "Error al descargar archivo")
        _error(mensaje)
        marcar_progreso(df, idx, "error", mensaje, folio_sugo, fase)
        return

    await page_sugo.bring_to_front()
    results_carga_oficio = await cargar_oficio_sugo(
        page=page_sugo,
        folio_sugo=folio_sugo,
        archivo_oficio=results_descarga_archivo["ruta"],
    )
    if results_carga_oficio.get("status") != "ok":
        mensaje = results_carga_oficio.get("message", "Error al cargar el oficio; requiere carga manual.")
        _error(mensaje)
        marcar_progreso(df, idx, "error", mensaje, folio_sugo, fase)
        return

    _ok("Oficio registrado y cargado correctamente.")
    marcar_progreso(
        df,
        idx,
        "ok",
        results_carga_oficio.get("message", "Oficio cargado correctamente"),
        folio_sugo,
        "archivo_cargado",
    )


async def orchestrator(df: pd.DataFrame, modo_oculto: bool):
    try:
        _section("Preparación")

        if os.path.exists(DIR_ARCHIVOS):
            shutil.rmtree(DIR_ARCHIVOS)
        
        DIR_ARCHIVOS.mkdir(parents=True, exist_ok=True)
        DIST_DIR.mkdir(parents=True, exist_ok=True)

        user, password = cargar_credenciales_sugo()
        _ok("Credenciales SUGO cargadas.")

        df[PROGRESS_STATUS_COLUMN] = df[PROGRESS_STATUS_COLUMN].fillna("").astype(str)
        pending_folios = df[df[PROGRESS_STATUS_COLUMN].str.lower() != "ok"]
        total_pending = len(pending_folios)
        _info(f"Oficios pendientes: {total_pending} de {len(df)}.")

        if total_pending == 0:
            _ok("No hay oficios pendientes por procesar.")
            guardar_progreso(df)
            return

        async with async_playwright() as p:
            _section("Navegador", "Abriendo Chrome persistente para SUGO")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=modo_oculto,
                channel="chrome",
                args=ARGUMENTOS_CHROME,
            )

            context, page_drive = await load_page_drive(context, p, modo_oculto)

            if not page_drive:
                _error("No se pudo abrir Google Drive")
                await context.close()
                return

            page_sugo = await load_page_sugo(context, user, password)

            if not page_sugo:
                _error("No se pudo abrir SUGO, Revisar credenciales...")
                await context.close()
                return

            try:
                for i, (idx, row) in enumerate(pending_folios.iterrows(), start=1):
                    try:
                        await procesar_oficio(
                            df=df,
                            idx=idx,
                            row=row,
                            numero=i,
                            total=total_pending,
                            page_sugo=page_sugo,
                            page_drive=page_drive,
                        )
                    except Exception as exc:
                        folio_existente = str(df.at[idx, "folio_sugo"] or "").strip()
                        mensaje = f"Error inesperado en el oficio: {exc}"
                        _error(mensaje)
                        marcar_progreso(df, idx, "error", mensaje, folio_existente)

                    if i % BATCH_GUARDADO == 0:
                        guardar_progreso(df)
                        _ok(f"Guardado incremental completado ({i}/{total_pending}).")
            except Exception as exc:
                _error(f"Error al procesar el lote: {exc}")
            finally:
                guardar_progreso(df)
                _LOG_INDENT.set(0)
                _section("Cierre")
                _ok(
                    f"Proceso finalizado. Resultados guardados en: {TEMP_FILE}"
                )
                await context.close()

    except Exception as e:
        _error(f"Error crítico en el proceso: {e}")

    finally:
        if os.path.exists(DIR_ARCHIVOS):
            shutil.rmtree(DIR_ARCHIVOS)


async def ejecutar_rpa_async(ruta_json: Path, modo_oculto: bool):
    """Función principal asíncrona invocada por la GUI o CLI."""
    try:
        _section("Inicio de registro de oficios", f"Fuente: {ruta_json}")
        df = cargar_oficios(ruta_json)
        guardar_progreso(df)
        _info(f"Registros cargados: {len(df)}")
        await orchestrator(df, modo_oculto=modo_oculto)
    except Exception as e:
        _error(f"No se pudo iniciar el proceso: {e}")


# =========================================================
#   INTERFAZ GRÁFICA ESTILO BBVA (CustomTkinter)
# =========================================================

# Paleta de Colores Institucional BBVA
BBVA_NAVY        = "#072146"  # Azul Marino Corporativo Principal
BBVA_CORE_BLUE   = "#004481"  # Azul Core BBVA
BBVA_MEDIUM_BLUE = "#1973B8"  # Azul Medio Interactivo
BBVA_AQUA        = "#2DCCCD"  # Turquesa / Aqua BBVA (Acentos y Toggles)
BBVA_BG_LIGHT    = "#F4F6F9"  # Fondo Gris Azulado Claro Corporativo
BBVA_WHITE       = "#FFFFFF"  # Blanco para tarjetas
BBVA_TEXT_PRIMARY= "#121212"  # Texto oscuro
BBVA_TEXT_MUTED  = "#5A6872"  # Texto secundario
BBVA_CONSOLE_BG  = "#04162E"  # Fondo oscuro consola estilo terminal BBVA


class RedirectConsole:
    """Redirige stdout y stderr hacia una cola segura para hilos (Thread-safe)."""
    def __init__(self, log_queue: queue.Queue, original_stream):
        self.log_queue = log_queue
        self.original_stream = original_stream

    def write(self, message: str):
        if self.original_stream:
            try:
                self.original_stream.write(message)
            except Exception:
                pass
        if message:
            self.log_queue.put(message)

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass


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
        global INPUT_JSON_FILE
        INPUT_JSON_FILE = ruta_json
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


if __name__ == "__main__":
    # Permite seguir ejecutando por CLI si se pasa el argumento --cli
    if "--cli" in sys.argv:
        modo_oculto_cli = "--headless" in sys.argv or "--oculto" in sys.argv
        asyncio.run(ejecutar_rpa_async(INPUT_JSON_FILE, modo_oculto_cli))
    else:
        app = BBVARpaApp()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()