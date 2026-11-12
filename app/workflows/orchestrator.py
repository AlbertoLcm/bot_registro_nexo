"""Orquesta las fases de cada oficio con 2 contextos simultáneos validando Drive en un solo Chrome."""
import asyncio
import os
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import BrowserContext, Page, async_playwright

from app.config import (
    ARGUMENTOS_CHROME, BATCH_GUARDADO, DIR_ARCHIVOS, DIST_DIR,
    PROGRESS_STATUS_COLUMN, TEMP_FILE, URL_GOOGLE_DRIVE, USER_DATA_DIR,
)
from app.core.notifier import notificar_fin_rpa
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

NUM_WORKERS = 2  # Número de contextos simultáneos


async def procesar_oficio(
    df: pd.DataFrame,
    idx,
    row: pd.Series,
    numero: int,
    total: int,
    page_sugo: Page,
    page_drive: Page,
    dir_descarga_worker: Path,
    df_lock: asyncio.Lock,
    worker_id: int,
) -> None:
    """Procesa un oficio y persiste cada fase de forma segura entre workers."""
    data_oficio = row.to_dict()

    oficio_autoridad         = str(data_oficio.get("oficio_autoridad") or "").strip()
    expediente_autoridad     = str(data_oficio.get("expediente_autoridad") or "").strip()
    instrucciones_oficio     = str(data_oficio.get("instrucciones_oficio") or "").strip() + "____INSTRUCCIONES_GENERADAS_POR_EL_BOT_DE_REGISTRO"
    origen_folio             = str(data_oficio.get("origen_folio") or "").strip()
    tipo_oficio              = str(data_oficio.get("tipo_oficio") or "").strip()
    autoridad_especifica     = str(data_oficio.get("autoridad_especifica") or "").strip()
    region                   = str(data_oficio.get("region") or "").strip()
    plaza                    = str(data_oficio.get("plaza") or "").strip()
    autoridad                = str(data_oficio.get("autoridad") or "").strip()
    subautoridad_abreviada   = str(data_oficio.get("subautoridad_abreviada") or "").strip()
    oficio_subautoridad      = str(data_oficio.get("oficio_subautoridad") or "").strip()
    expediente_subautoridad  = str(data_oficio.get("expediente_subautoridad") or "").strip()
    fecha_recepcion_original = str(data_oficio.get("fecha_recepcion") or "").strip()
    abogado_solicitante      = str(data_oficio.get("abogado_solicitante") or "").strip().upper()
    empresa                  = str(data_oficio.get("empresa") or "").strip()
    tipo_operacion           = str(data_oficio.get("tipo_operacion") or "").strip()
    file_name                = str(data_oficio.get("name_file") or data_oficio.get("nombre_archivo") or "").strip()
    file_url                 = str(data_oficio.get("url_archivo") or "").strip()
    clientes_objetivo        = data_oficio.get("clientes_objetivo") or []
    plazo                    = data_oficio.get("plazo") or {}
    fase                     = str(data_oficio.get("fase_proceso") or "").strip().lower()
    folio_sugo               = str(data_oficio.get("folio_sugo") or "").strip()

    _section(
        f"[W{worker_id}] Oficio {numero}/{total}",
        f"{oficio_autoridad} | Expediente: {expediente_autoridad}",
    )
    _LOG_INDENT.set(1)
    _info(f"[W{worker_id}] Origen: {origen_folio} | Tipo: {tipo_oficio}")

    # =============== Estandarización y limpieza de datos del oficio ===============
    # fecha_recepcion = estandarizar_fechas(fecha_recepcion_original)
    # NO USAMOS LA FECHA ORIGINAL POR REGLAS DE NEGOCIO; SIEMPRE SE USARÁ LA FECHA ACTUAL PARA EL REGISTRO EN SUGO
    fecha_recepcion = ""

    if not fecha_recepcion:
        _warn(f"[W{worker_id}] Fecha de recepción vacía o inválida. Se usará la fecha actual.")
        fecha_recepcion = datetime.now().strftime("%Y-%m-%d")
    fecha_recepcion = datetime.strptime(fecha_recepcion, "%Y-%m-%d").strftime("%d/%m/%Y")

    timestamp = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-W{worker_id}"
    if not oficio_autoridad:
        oficio_autoridad = f"S/N-{timestamp}"
    if not expediente_autoridad:
        expediente_autoridad = f"S/N-{timestamp}"
    plazo_dias = calcular_plazo_dias(plazo)

    if tipo_oficio == "JUDICIAL":
        autoridad = "TRIBUNAL SUPERIOR DE JUSTICIA"
        autoridad_especifica = ""

    if not tipo_operacion:
        _warn(f"[W{worker_id}] Tipo de operación vacío. Se asignará 'ANALISIS' por defecto.")
        tipo_operacion = "insumos"
    # ==============================================================================

    if fase == "archivo_cargado":
        async with df_lock:
            marcar_progreso(df, idx, "ok", "Oficio ya cargado en SUGO.", folio_sugo, fase)
        return

    # Limpiar archivos previos del directorio exclusivo de este worker
    for f_old in dir_descarga_worker.glob("*"):
        if f_old.is_file():
            try:
                f_old.unlink()
            except Exception:
                pass

    # Iniciar la descarga desde Drive en paralelo mientras SUGO captura las fases 1, 2 y 3
    tarea_descarga = asyncio.create_task(
        descargar_archivo(page_drive, file_url, dir_descarga_worker)
    )

    try:
        # --- FASE 1: ALTA DE OFICIO ---
        if not folio_sugo:
            async with df_lock:
                marcar_progreso(df, idx, "procesando", "Iniciando alta de oficio", fase="pendiente")

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
                _error(f"[W{worker_id}] {mensaje}")
                async with df_lock:
                    marcar_progreso(df, idx, "error", mensaje, fase="pendiente")
                return

            folio_sugo = results_alta["folio_sugo"]
            fase = "oficio_alta"
            async with df_lock:
                marcar_progreso(df, idx, "procesando", results_alta.get("message", ""), folio_sugo, fase)
        elif not fase:
            fase = "oficio_alta"
            _warn(f"[W{worker_id}] Se reanudará el folio existente {folio_sugo} desde alta de personas.")
            async with df_lock:
                marcar_progreso(df, idx, "procesando", "Reanudando folio existente.", folio_sugo, fase)

        # --- FASE 2: ALTA DE PERSONAS ---
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
                _error(f"[W{worker_id}] {mensaje}")
                async with df_lock:
                    marcar_progreso(df, idx, "error", mensaje, folio_sugo, fase)
                return

            fase = "personas_alta"
            async with df_lock:
                marcar_progreso(df, idx, "procesando", results_clientes.get("message", ""), folio_sugo, fase)

        # --- FASE 3: FINALIZACIÓN DE CAPTURA ---
        if fase != "captura_finalizada":
            results_finalizacion = await registro_finalizar_captura(page=page_sugo, folio_sugo=folio_sugo)
            if results_finalizacion.get("status") != "ok":
                mensaje = results_finalizacion.get("message", "Error al finalizar captura")
                _error(f"[W{worker_id}] {mensaje}")
                async with df_lock:
                    marcar_progreso(df, idx, "error", mensaje, folio_sugo, fase)
                return

            fase = "captura_finalizada"
            async with df_lock:
                marcar_progreso(df, idx, "procesando", results_finalizacion.get("message", ""), folio_sugo, fase)

        # --- FASE 4: ESPERAR DESCARGA DE DRIVE Y CARGAR ARCHIVO EN SUGO (IMAX) ---
        results_descarga_archivo = await tarea_descarga
        if results_descarga_archivo.get("status") != "ok":
            mensaje = results_descarga_archivo.get("message", "Error al descargar archivo")
            _error(f"[W{worker_id}] {mensaje}")
            async with df_lock:
                marcar_progreso(df, idx, "error", mensaje, folio_sugo, fase)
            return

        results_carga_oficio = await cargar_oficio_sugo(
            page=page_sugo,
            folio_sugo=folio_sugo,
            archivo_oficio=results_descarga_archivo["ruta"],
        )
        if results_carga_oficio.get("status") != "ok":
            mensaje = results_carga_oficio.get("message", "Error al cargar el oficio; requiere carga manual.")
            _error(f"[W{worker_id}] {mensaje}")
            async with df_lock:
                marcar_progreso(df, idx, "error", mensaje, folio_sugo, fase)
            return

        _ok(f"[W{worker_id}] Oficio {folio_sugo} registrado y cargado correctamente.")
        async with df_lock:
            marcar_progreso(
                df,
                idx,
                "ok",
                results_carga_oficio.get("message", "Oficio cargado correctamente"),
                folio_sugo,
                "archivo_cargado",
            )

    finally:
        if not tarea_descarga.done():
            tarea_descarga.cancel()
            try:
                await tarea_descarga
            except (asyncio.CancelledError, Exception):
                pass


async def consumir_cola_worker(
    worker_id: int,
    cola: asyncio.Queue,
    df: pd.DataFrame,
    total_pending: int,
    page_sugo: Page,
    page_drive: Page,
    df_lock: asyncio.Lock,
    estado_workers: dict,
):
    """Consume oficios de la cola utilizando las páginas ya autenticadas del worker."""
    dir_descarga_worker = DIR_ARCHIVOS / f"worker_{worker_id}"
    dir_descarga_worker.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            numero, idx, row = cola.get_nowait()
        except asyncio.QueueEmpty:
            break

        try:
            await procesar_oficio(
                df=df,
                idx=idx,
                row=row,
                numero=numero,
                total=total_pending,
                page_sugo=page_sugo,
                page_drive=page_drive,
                dir_descarga_worker=dir_descarga_worker,
                df_lock=df_lock,
                worker_id=worker_id,
            )
        except Exception as exc:
            async with df_lock:
                folio_existente = str(df.at[idx, "folio_sugo"] or "").strip()
                mensaje = f"Error inesperado en el oficio: {exc}"
                _error(f"[W{worker_id}] {mensaje}")
                marcar_progreso(df, idx, "error", mensaje, folio_existente)
        finally:
            async with df_lock:
                estado_workers["procesados"] += 1
                procesados_actual = estado_workers["procesados"]
                if procesados_actual % BATCH_GUARDADO == 0:
                    guardar_progreso(df)
                    _ok(f"Guardado incremental completado ({procesados_actual}/{total_pending}).")
            cola.task_done()


async def preparar_contexto_secundario(
    worker_id: int,
    p,
    modo_oculto: bool,
    cookies_drive: list[dict],
    user: str,
    password: str,
):
    """
    Crea un navegador secundario para el Worker 2+, le inyecta las cookies ya validadas
    de Google Drive del Worker 1 (sin pedir login otra vez) y abre SUGO.
    """
    _section(f"Navegador Worker {worker_id}", "Creando contexto secundario con sesión heredada")
    browser = await p.chromium.launch(
        headless=modo_oculto,
        channel="chrome",
        args=ARGUMENTOS_CHROME,
    )
    context = await browser.new_context()

    try:
        # Inyectamos todas las cookies de Google Drive recién validadas en el Worker 1
        await context.add_cookies(cookies_drive)

        page_drive = await context.new_page()
        await page_drive.goto(URL_GOOGLE_DRIVE, timeout=30_000)
        await page_drive.wait_for_load_state("domcontentloaded")

        if "accounts.google" in page_drive.url or "idp/profile" in page_drive.url:
            _warn(f"[W{worker_id}] El contexto secundario no pudo heredar la sesión de Drive.")
            await context.close()
            await browser.close()
            return None, None, None

        page_sugo = await load_page_sugo(context, user, password)
        if not page_sugo:
            _error(f"[W{worker_id}] No se pudo abrir SUGO en el contexto secundario.")
            await context.close()
            await browser.close()
            return None, None, None

        _ok(f"[W{worker_id}] Contexto secundario listo.")
        return context, page_sugo, page_drive

    except Exception as e:
        _error(f"[W{worker_id}] Error al inicializar contexto secundario: {e}")
        await context.close()
        await browser.close()
        return None, None, None


async def orchestrator(df: pd.DataFrame, modo_oculto: bool):
    _section("Preparación")
    exito_global = True
    mensaje_notificacion = "El proceso ha finalizado."

    try:
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
            mensaje_notificacion = "No había oficios pendientes por procesar."
            return

        async with async_playwright() as p:
            context_principal = None
            contextos_secundarios: list[BrowserContext] = []

            try:
                # 1. ABRIR Y VALIDAR SESIÓN DE DRIVE EN UN SOLO CHROME (WORKER 1)
                _section("Navegador Principal (Worker 1)", "Validando sesión de Google Drive y SUGO")
                context_principal = await p.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=modo_oculto,
                    channel="chrome",
                    args=ARGUMENTOS_CHROME,
                )

                # Aquí se ejecuta tu load_page_drive exacto: si pide login, abre 1 solo Chrome visible
                context_principal, page_drive_1 = await load_page_drive(
                    context_principal, p, modo_oculto
                )

                if not page_drive_1:
                    _error("No se pudo abrir Google Drive.")
                    exito_global = False
                    mensaje_notificacion = "Error: No se pudo abrir Google Drive."
                    return

                page_sugo_1 = await load_page_sugo(context_principal, user, password)
                if not page_sugo_1:
                    _error("No se pudo abrir SUGO, revisar credenciales...")
                    exito_global = False
                    mensaje_notificacion = "Error: No se pudo iniciar sesión en SUGO."
                    return

                # Extraemos las cookies ya validadas (incluyendo las de Google Drive)
                cookies_sesion = await context_principal.cookies()

                # 2. PREPARAR COLA DE OFICIOS
                cola = asyncio.Queue()
                for i, (idx, row) in enumerate(pending_folios.iterrows(), start=1):
                    cola.put_nowait((i, idx, row))

                df_lock = asyncio.Lock()
                estado_workers = {"procesados": 0}

                tareas_workers = [
                    consumir_cola_worker(
                        worker_id=1,
                        cola=cola,
                        df=df,
                        total_pending=total_pending,
                        page_sugo=page_sugo_1,
                        page_drive=page_drive_1,
                        df_lock=df_lock,
                        estado_workers=estado_workers,
                    )
                ]

                # 3. SI HAY MÁS DE 1 OFICIO, LEVANTAMOS EL WORKER 2 HEREDANDO LAS COOKIES
                workers_objetivo = min(NUM_WORKERS, total_pending)
                for w_id in range(2, workers_objetivo + 1):
                    ctx_sec, page_sugo_sec, page_drive_sec = await preparar_contexto_secundario(
                        worker_id=w_id,
                        p=p,
                        modo_oculto=modo_oculto,
                        cookies_drive=cookies_sesion,
                        user=user,
                        password=password,
                    )
                    if ctx_sec and page_sugo_sec and page_drive_sec:
                        contextos_secundarios.append(ctx_sec)
                        tareas_workers.append(
                            consumir_cola_worker(
                                worker_id=w_id,
                                cola=cola,
                                df=df,
                                total_pending=total_pending,
                                page_sugo=page_sugo_sec,
                                page_drive=page_drive_sec,
                                df_lock=df_lock,
                                estado_workers=estado_workers,
                            )
                        )
                    else:
                        _warn(f"No se pudo levantar el Worker {w_id}; el Worker 1 procesará toda la carga.")

                # 4. EJECUTAR AMBOS WORKERS EN PARALELO
                await asyncio.gather(*tareas_workers)

            except Exception as exc:
                _error(f"Error al procesar el lote: {exc}")
                exito_global = False
            finally:
                guardar_progreso(df)
                _LOG_INDENT.set(0)
                _section("Cierre")
                _ok(f"Proceso finalizado. Resultados guardados en: {TEMP_FILE}")

                for ctx_sec in contextos_secundarios:
                    try:
                        browser_sec = ctx_sec.browser
                        await ctx_sec.close()
                        if browser_sec:
                            await browser_sec.close()
                    except Exception:
                        pass

                if context_principal:
                    try:
                        await context_principal.close()
                    except Exception:
                        pass

        # Calcular resumen final de oficios para la notificación
        completados = (df[PROGRESS_STATUS_COLUMN].str.lower() == "ok").sum()
        errores = (df[PROGRESS_STATUS_COLUMN].str.lower() == "error").sum()

        if errores > 0:
            exito_global = False
            mensaje_notificacion = f"Finalizado con {errores} error(es) y {completados} completados."
        else:
            mensaje_notificacion = f"Se completaron los {completados} oficios correctamente."

    except Exception as e:
        _error(f"Error crítico en el proceso: {e}")
        exito_global = False
        mensaje_notificacion = f"Error crítico: {str(e)[:60]}"

    finally:
        if os.path.exists(DIR_ARCHIVOS):
            shutil.rmtree(DIR_ARCHIVOS, ignore_errors=True)

        titulo_notif = "BOT Finalizado" if exito_global else "BOT Finalizado con Alertas"
        notificar_fin_rpa(
            titulo=titulo_notif,
            mensaje=mensaje_notificacion,
            exito=exito_global,
        )


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
        notificar_fin_rpa(
            titulo="Error al iniciar RPA",
            mensaje=f"No se pudo cargar el archivo de oficios: {str(e)[:60]}",
            exito=False,
        )