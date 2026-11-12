"""Carga del documento de oficio al repositorio de SUGO."""
import asyncio
from pathlib import Path
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from app.config import URL_SUGO_ESTATUS
from app.core.logging import _error, _info, _log_indent, _ok, _subsection, _warn


async def cargar_oficio_sugo(
    page: Page,
    *,
    folio_sugo: str,
    archivo_oficio: str,
):
    folio_limpio = str(folio_sugo or "").strip()
    _subsection("Carga Oficio", f"Folio SUGO: {folio_limpio}")

    with _log_indent():
        if not folio_limpio:
            _error("Falta el Folio SUGO.")
            return {
                "status": "error",
                "message": "Falta el Folio SUGO.",
            }

        if not archivo_oficio:
            _error("No se proporcionó la ruta del archivo del oficio.")
            return {
                "status": "error",
                "message": "No se proporcionó la ruta del archivo.",
            }

        file_oficio = Path(archivo_oficio)
        if not file_oficio.exists() or not file_oficio.is_file():
            _error(f"No se encontró el archivo: {file_oficio}")
            return {
                "status": "error",
                "message": f"No se encontró el archivo: {file_oficio.name}",
            }

        page_repositorio = None
        pagina_upload = None

        try:
            _info("Abriendo módulo de estatus SUGO.")
            await page.goto(URL_SUGO_ESTATUS, wait_until="domcontentloaded", timeout=60_000)

            _info(f"Buscando folio SUGO: {folio_limpio}")
            checkbox = page.locator("#rSugo")
            await checkbox.wait_for(state="visible")
            await checkbox.click()

            await page.fill("#fSugo", folio_limpio)

            async with page.expect_navigation(timeout=15_000):
                await page.evaluate("buscar()")

            await page.wait_for_selector("#tablaResultados", timeout=5_000)

            fila_folio = (
                page.locator("#tablaResultados tr")
                .filter(has_text=folio_limpio)
                .filter(has=page.locator("input[name='Tipo'][type='radio']"))
                .first
            )

            if await fila_folio.count() == 0:
                _error(f"El folio '{folio_limpio}' no apareció en la tabla de resultados.")
                return {
                    "status": "error",
                    "message": f"El folio '{folio_limpio}' no se encontró en Estatus SUGO.",
                }

            checkbox_folio = fila_folio.locator("input[name='Tipo'][type='radio']").first
            await checkbox_folio.wait_for(state="visible")
            await checkbox_folio.check()

            # --- Abrir visor IMAX ---
            try:
                _info("Abriendo visor IMAX (repositorio).")
                await page.locator("#btnIMAX").click()

                for _ in range(15):  # Hasta 7.5 segundos buscando la ventana emergente
                    for p in page.context.pages:
                        if p != page and not p.is_closed() and "image-viewer.jsp" in p.url:
                            page_repositorio = p
                            break
                    if page_repositorio:
                        break
                    await asyncio.sleep(0.5)

                if not page_repositorio:
                    _error("No se detectó la ventana del repositorio IMAX.")
                    return {
                        "status": "error",
                        "message": "No se pudo abrir el repositorio de SUGO, verifica la VPN.",
                    }

                await page_repositorio.wait_for_load_state("domcontentloaded", timeout=30_000)

            except Exception as e:
                _error(f"Error al abrir el repositorio de SUGO: {e}")
                return {
                    "status": "error",
                    "message": f"Error inesperado al abrir el repositorio de SUGO: {e}",
                }

            # --- Abrir popup de carga de archivo ---
            _info("Abriendo ventana de carga de documento.")
            frame_visor = page_repositorio.frame_locator('frame[name="viewerFrame"]')
            link_upload = frame_visor.locator('a[href="javascript:imageManager(2)"]')
            await link_upload.wait_for(state="visible", timeout=15_000)

            async with page_repositorio.context.expect_page(timeout=15_000) as upload_popup_info:
                await link_upload.click()

            pagina_upload = await upload_popup_info.value
            await pagina_upload.wait_for_load_state("domcontentloaded", timeout=30_000)

            _info(f"Cargando archivo: {file_oficio.name}")
            input_file0 = pagina_upload.locator("#file0")
            await input_file0.wait_for(state="visible", timeout=10_000)
            await input_file0.set_input_files(file_oficio)

            await pagina_upload.locator("input[type='submit']").click()

            try:
                await pagina_upload.wait_for_event("close", timeout=90_000)
            except PlaywrightTimeoutError:
                _error("La ventana de carga no se cerró tras 90s; la subida pudo haber fallado.")
                return {
                    "status": "error",
                    "message": "Tiempo de espera agotado al subir el archivo en IMAX.",
                }

            _ok("Oficio cargado exitosamente en el repositorio de SUGO.")
            return {
                "status": "ok",
                "message": "Se cargó exitosamente el oficio en SUGO.",
            }

        except PlaywrightTimeoutError as e:
            texto_error_sistema = "No se detectó el mensaje de éxito (Timeout)"

            try:
                if await page.locator("#BTACEPTAR").is_visible():
                    texto_error_sistema = await page.locator(
                        ".TextoAlerta .txtAlertArqVN"
                    ).inner_text()
                    _warn(f"Alerta de SUGO detectada: {texto_error_sistema}")

                    async with page.expect_navigation(timeout=10_000):
                        await page.click("#BTACEPTAR")
            except Exception:
                pass

            _error(f"Timeout en carga de oficio: {texto_error_sistema} ({e})")
            return {
                "status": "error",
                "message": texto_error_sistema,
            }

        except Exception as e:
            _error(f"Error inesperado al cargar oficio en SUGO: {e}")
            return {
                "status": "error",
                "message": f"Ocurrió un error inesperado en el portal de SUGO: {e}",
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

            try:
                if not page.is_closed():
                    await page.bring_to_front()
            except Exception:
                pass