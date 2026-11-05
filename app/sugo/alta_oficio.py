"""Captura del oficio inicial en SUGO."""
import asyncio
from pathlib import Path
from playwright.async_api import Page
from app.config import URL_ALTA_OFICIO
from app.core.logging import _error, _info, _log_indent, _ok, _subsection, _warn
from app.sugo.selectors import select_best_option


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
