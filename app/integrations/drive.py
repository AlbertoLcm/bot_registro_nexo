"""Descarga de documentos desde Google Drive usando Playwright."""
import asyncio
import os
from playwright.async_api import Page


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
