"""Finalización de la captura de un oficio en SUGO."""
import asyncio
from playwright.async_api import Page
from app.config import URL_FINALIZAR_CAPTURA
from app.core.logging import _error, _info, _log_indent, _ok, _subsection
from app.core.text import normalizar_texto


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
