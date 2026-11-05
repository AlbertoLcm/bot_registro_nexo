"""Carga del documento de oficio al repositorio de SUGO."""
import asyncio
from pathlib import Path
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from app.config import URL_SUGO_ESTATUS
from app.core.logging import _subsection


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
