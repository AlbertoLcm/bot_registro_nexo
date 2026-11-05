"""Carga de credenciales SUGO desde el archivo local configurado."""
import json
from typing import Tuple
from app.config import ARCHIVO_CREDENCIALES
from app.core.logging import _error


def cargar_credenciales_sugo() -> Tuple[str, str]:
    """Carga usuario y contraseña del archivo JSON."""
    try:
        with open(ARCHIVO_CREDENCIALES, "r", encoding="utf-8") as f:
            creds = json.load(f)
        return creds["user"], creds["password"]
    except FileNotFoundError:
        msg = f"No se encontró el archivo '{ARCHIVO_CREDENCIALES}'."
        _error(msg)
        raise FileNotFoundError(msg)
    except KeyError as exc:
        msg = f"Formato de credenciales inválido. Falta la clave {exc}."
        _error(msg)
        raise KeyError(msg)
    except Exception as exc:
        msg = f"Error inesperado al cargar credenciales: {exc}"
        _error(msg)
        raise RuntimeError(msg)
