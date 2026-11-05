"""Lectura y escritura de oficios, con progreso reanudable."""
import ast
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from app.config import (
    DIST_DIR, INPUT_JSON_FILE, TEMP_FILE, PROGRESS_COLUMNS,
    PROGRESS_STATUS_COLUMN, PROGRESS_KEY_COLUMNS, PROGRESS_ID_COLUMN,
)
from app.core.logging import _info, _ok, _warn


def _parse_clientes_objetivo(value):
    if isinstance(value, list):
        return value
    if pd.isnull(value):
        return []
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError, SyntaxError):
            try:
                parsed = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return []
        return parsed if isinstance(parsed, list) else []
    return []


def asegurar_ids_progreso(df: pd.DataFrame) -> pd.DataFrame:
    """Asigna un identificador estable por ocurrencia para no mezclar duplicados."""
    if PROGRESS_ID_COLUMN in df.columns:
        return df

    oficio = df.get("oficio_autoridad", pd.Series("", index=df.index)).fillna("").astype(str)
    expediente = df.get("expediente_autoridad", pd.Series("", index=df.index)).fillna("").astype(str)
    llave_base = oficio.str.strip() + "|" + expediente.str.strip()
    df[PROGRESS_ID_COLUMN] = llave_base + "|" + llave_base.groupby(llave_base).cumcount().astype(str)
    return df


def guardar_progreso(df: pd.DataFrame) -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    df_guardado = df.copy()

    if "clientes_objetivo" in df_guardado.columns:
        df_guardado["clientes_objetivo"] = df_guardado["clientes_objetivo"].apply(
            lambda value: json.dumps(_parse_clientes_objetivo(value), ensure_ascii=False)
        )

    df_guardado.to_csv(TEMP_FILE, index=False, encoding="utf-8-sig")


def cargar_oficios(ruta_json: Optional[Path] = None) -> pd.DataFrame:
    """Carga los oficios desde el archivo JSON seleccionado o el archivo por defecto."""
    archivo_entrada = Path(ruta_json) if ruta_json else INPUT_JSON_FILE

    if not archivo_entrada.exists():
        raise FileNotFoundError(f"No se encontró el archivo '{archivo_entrada}'.")

    _info(f"Leyendo archivo de entrada: {archivo_entrada}")
    with open(archivo_entrada, "r", encoding="utf-8") as f:
        registros = json.load(f)

    if not isinstance(registros, list):
        raise ValueError("El archivo JSON debe contener una lista de registros.")

    df = pd.DataFrame(registros)
    asegurar_ids_progreso(df)
    for column in PROGRESS_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    if "clientes_objetivo" not in df.columns:
        df["clientes_objetivo"] = [[] for _ in range(len(df))]
    else:
        df["clientes_objetivo"] = df["clientes_objetivo"].apply(_parse_clientes_objetivo)

    if TEMP_FILE.exists():
        _info(f"Se encontró progreso previo: {TEMP_FILE}")
        df_temp = pd.read_csv(TEMP_FILE, dtype=str, keep_default_na=False)
        asegurar_ids_progreso(df_temp)
        for column in PROGRESS_COLUMNS:
            if column not in df_temp.columns:
                df_temp[column] = ""

        merge_keys = [column for column in PROGRESS_KEY_COLUMNS if column in df.columns and column in df_temp.columns]
        if merge_keys:
            progress = df_temp[merge_keys + PROGRESS_COLUMNS].drop_duplicates(
                subset=merge_keys,
                keep="last",
            )
            df = df.merge(progress, on=merge_keys, how="left", suffixes=("", "_progreso"))

            for column in PROGRESS_COLUMNS:
                progress_column = f"{column}_progreso"
                if progress_column in df.columns:
                    df[column] = df[progress_column].fillna(df[column])
                    df.drop(columns=[progress_column], inplace=True)
            _ok("Progreso previo combinado con los oficios de entrada.")
        else:
            _warn("No se pudo combinar el progreso previo: faltan columnas llave.")

    df[PROGRESS_STATUS_COLUMN] = df[PROGRESS_STATUS_COLUMN].fillna("").astype(str)
    return df


def marcar_progreso(
    df: pd.DataFrame,
    idx,
    status: str,
    mensaje: str = "",
    folio_sugo: str = "",
    fase: Optional[str] = None,
) -> None:
    df.at[idx, PROGRESS_STATUS_COLUMN] = status
    df.at[idx, "mensaje"] = mensaje
    df.at[idx, "fecha_actualizacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if folio_sugo:
        df.at[idx, "folio_sugo"] = folio_sugo
    if fase is not None:
        df.at[idx, "fase_proceso"] = fase
    guardar_progreso(df)
    detalle_folio = f" | Folio SUGO: {folio_sugo}" if folio_sugo else ""
    detalle_mensaje = f" | {mensaje}" if mensaje else ""
    _info(f"Progreso actualizado: {status}{detalle_folio}{detalle_mensaje}")
