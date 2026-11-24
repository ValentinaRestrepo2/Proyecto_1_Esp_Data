"""Inferencia: carga el modelo VIGENTE del registro (alias `champion`) y predice.

El modelo se carga por alias desde MLflow, no desde un archivo copiado: lo que sirven
la API y la app es exactamente la versión que aprobó la compuerta de promoción. Se
carga una sola vez y queda en memoria.
"""

from __future__ import annotations

import pandas as pd

from proyecto_1_esp_data import config
from proyecto_1_esp_data.features import COLUMNAS_X, NUMERICAS

_pipeline = None
_version: str | None = None


def _cargar_vigente():
    """Trae del registro el modelo con alias `champion`: (pipeline, versión)."""
    # Se importa aquí: MLflow tarda unos segundos en cargar y no hace falta si el
    # modelo ya está en memoria.
    import mlflow

    from proyecto_1_esp_data import registro

    mv = registro.version_por_alias(registro.cliente(), config.ALIAS_VIGENTE)
    if mv is None:
        raise FileNotFoundError(
            "No hay modelo vigente. Ejecuta `make train` y luego `make promote`."
        )
    uri = f"models:/{config.MODELO_REGISTRADO}@{config.ALIAS_VIGENTE}"
    return mlflow.sklearn.load_model(uri), str(mv.version)


def obtener_pipeline():
    """Carga el modelo vigente una sola vez y lo guarda en memoria."""
    global _pipeline, _version
    if _pipeline is None:
        _pipeline, _version = _cargar_vigente()
    return _pipeline


def version_modelo() -> str | None:
    """Versión del modelo vigente en el registro (None si todavía no hay)."""
    return _version


def modelo_disponible() -> bool:
    try:
        obtener_pipeline()
    except FileNotFoundError:
        return False
    return True


def predecir(datos: dict) -> dict:
    """Esta función predice para una sola muestra"""
    faltantes = [c for c in COLUMNAS_X if c not in datos]
    if faltantes:
        raise ValueError(f"Faltan columnas: {faltantes}")

    df = pd.DataFrame([datos], columns=COLUMNAS_X).astype(
        {c: float for c in NUMERICAS}  # None -> NaN, que el imputador maneja
    )
    p = float(obtener_pipeline().predict_proba(df)[0, 1])
    return {
        "probabilidad_pm25_mala_manana": round(p, 4),
        "mala_calidad_manana": p >= config.UMBRAL_DECISION,
        "umbral_pm25": config.UMBRAL_PM25,
    }
