"""Inferencia: carga perezosa del pipeline entrenado y predicción para una fila"""

from __future__ import annotations

import joblib
import pandas as pd

from proyecto_1_esp_data import config
from proyecto_1_esp_data.features import COLUMNAS_X, NUMERICAS

_pipeline = None


def obtener_pipeline():
    """Carga el modelo una sola vez y lo guarda en memoria."""
    global _pipeline
    if _pipeline is None:
        if not config.MODELO_PATH.exists():
            raise FileNotFoundError(
                f"No hay modelo en {config.MODELO_PATH}. Ejecuta `make train`."
            )
        _pipeline = joblib.load(config.MODELO_PATH)
    return _pipeline


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


ETIQUETAS_NIVEL = {
    "alto": "Mala calidad anticipada",
    "moderado": "Vigilar: riesgo moderado",
    "aceptable": "Calidad aceptable",
}


def clasificar_riesgo(resultado: dict) -> dict:
    """Convierte la predicción en un nivel de riesgo para mostrar al usuario.

    Regla de negocio, aquí y no en la app:
    - `alto`: el modelo predice día malo (probabilidad >= UMBRAL_DECISION).
    - `moderado`: no es día malo, pero la probabilidad alcanza UMBRAL_VIGILANCIA.
    - `aceptable`: el resto.
    """
    if resultado["mala_calidad_manana"]:
        nivel = "alto"
    elif resultado["probabilidad_pm25_mala_manana"] >= config.UMBRAL_VIGILANCIA:
        nivel = "moderado"
    else:
        nivel = "aceptable"
    return {"nivel": nivel, "etiqueta": ETIQUETAS_NIVEL[nivel]}
