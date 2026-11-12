"""Finalización de la captura de un oficio en SUGO."""
import asyncio
from playwright.async_api import Page
from app.config import URL_FINALIZAR_CAPTURA
from app.core.logging import _error, _info, _log_indent, _ok, _subsection, _warn
from app.core.text import normalizar_texto


async def registro_finalizar_captura(page: Page, folio_sugo: str):
    folio_limpio = str(folio_sugo or "").strip()
    if not folio_limpio:
        _error("No se proporcionó un folio SUGO válido para finalizar.")
        return {
            "status": "error",
            "message": "Folio SUGO vacío o inválido al intentar finalizar captura.",
        }

    try:
        _subsection("Finalización", f"Folio SUGO: {folio_limpio}")
        with _log_indent():
            _info("Abriendo formulario de finalización.")
            await page.goto(URL_FINALIZAR_CAPTURA, wait_until="domcontentloaded", timeout=60000)

            _info("Buscando oficio para finalizar captura.")
            checkbox_por_folio = page.locator("#porFolio")
            await checkbox_por_folio.wait_for(state="visible")
            await checkbox_por_folio.click()
            await page.fill("#noFolio", folio_limpio)

            async with page.expect_navigation(timeout=15000):
                await page.evaluate("buscar()")

            # Buscamos la fila que realmente contenga el folio para no finalizar uno equivocado
            fila_folio = (
                page.locator("tr")
                .filter(has_text=folio_limpio)
                .filter(has=page.locator("input[id^='checks']"))
                .last
            )

            if await fila_folio.count() == 0:
                _error(f"El folio '{folio_limpio}' no apareció en la tabla de finalización.")
                return {
                    "status": "error",
                    "message": f"El folio '{folio_limpio}' no se encontró para finalizar captura.",
                }

            checkbox_folio = fila_folio.locator("input[id^='checks']").first
            await checkbox_folio.wait_for(state="visible", timeout=5000)
            await checkbox_folio.check()
            _ok("Oficio seleccionado para finalizar.")

            await asyncio.sleep(0.5)

            loop = asyncio.get_running_loop()
            resultado_alerta = loop.create_future()

            async def aceptar_alerta(dialog):
                mensaje = dialog.message.strip()
                await dialog.accept()
                if not resultado_alerta.done():
                    resultado_alerta.set_result(mensaje)

            page.on("dialog", aceptar_alerta)
            try:
                _info("Enviando finalización de captura.")
                await page.locator("#btnFinCaptura").click()
                mensaje_alerta = await asyncio.wait_for(resultado_alerta, timeout=10)
            except asyncio.TimeoutError:
                # Verificamos si en lugar de alert() nativo apareció una alerta modal en el DOM
                if await page.is_visible(".TextoAlerta .txtAlertArqVN"):
                    texto_modal = await page.locator(".TextoAlerta .txtAlertArqVN").inner_text()
                    _warn(f"Aviso modal detectado al finalizar: {texto_modal}")
                    return {
                        "status": "error",
                        "message": f"SUGO mostró un aviso al finalizar: {texto_modal}",
                    }
                return {
                    "status": "error",
                    "message": "No se confirmó la finalización de captura (Timeout esperando alerta).",
                }
            finally:
                page.remove_listener("dialog", aceptar_alerta)

            alerta_normalizada = normalizar_texto(mensaje_alerta)
            if any(texto in alerta_normalizada for texto in ("error", "incorrect", "fall", "no se pudo")):
                _error(f"SUGO rechazó la finalización: {mensaje_alerta}")
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
            "message": f"Ocurrió un error inesperado al finalizar captura: {e}",
        }