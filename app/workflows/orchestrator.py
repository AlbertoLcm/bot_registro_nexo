"""Orquesta las fases de cada oficio y permite retomar los incompletos."""
import os
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import Page, async_playwright

from app.config import (
    ARGUMENTOS_CHROME, BATCH_GUARDADO, DIR_ARCHIVOS, DIST_DIR,
    PROGRESS_STATUS_COLUMN, TEMP_FILE, USER_DATA_DIR,
)
from app.core.credentials import cargar_credenciales_sugo
from app.core.logging import _LOG_INDENT, _section, _info, _ok, _warn, _error
from app.core.progress import cargar_oficios, guardar_progreso, marcar_progreso
from app.core.text import calcular_plazo_dias, estandarizar_fechas
from app.integrations.browser import load_page_drive, load_page_sugo
from app.integrations.drive import descargar_archivo
from app.sugo.alta_oficio import registro_alta_oficio
from app.sugo.alta_personas import registro_alta_persona
from app.sugo.finalizacion import registro_finalizar_captura
from app.sugo.documentos import cargar_oficio_sugo


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

    # =============== Estandarización y limpieza de datos del oficio =============== 

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

    if tipo_oficio == "JUDICIAL":
        autoridad = "TRIBUNAL SUPERIOR DE JUSTICIA"
        autoridad_especifica = ""

    # ================================================================== 



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
