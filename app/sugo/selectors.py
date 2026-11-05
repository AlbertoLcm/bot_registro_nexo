"""Selección tolerante a acentos, evitando coincidencias ambiguas."""
import re
import unicodedata
from playwright.async_api import Page
from app.core.logging import _ok


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
