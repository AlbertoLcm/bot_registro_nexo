"""Normalización de texto, fechas y plazos."""
import math
import unicodedata
from datetime import datetime
import pandas as pd


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

    if pd.isnull(fecha):
        return ""

    fecha = str(fecha).strip().lower()

    if fecha == "nat" or fecha == "":
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
        "%d %m %Y",
        "%m/%d/%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",  # NUEVO: ISO 8601 con milisegundos
        "%Y-%m-%dT%H:%M:%SZ",      # NUEVO: ISO 8601 sin milisegundos
        "%Y-%m-%dT%H:%M:%S%z",     # NUEVO: ISO 8601 con zona horaria
    ]

    for formato in formatos:
        try:
            fecha_obj = datetime.strptime(fecha, formato)
            return fecha_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return ""


def limpiar_texto(texto: str) -> str:
    if not texto:
        return ""
    texto = texto.lower()
    texto = "".join([c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"])
    return texto
