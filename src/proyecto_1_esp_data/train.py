"""Entrenamiento con split temporal, evaluación y guardado"""

from __future__ import annotations

import joblib
import pandas as pd

from proyecto_1_esp_data import config
from proyecto_1_esp_data.data import prepare
from proyecto_1_esp_data.features import COLUMNAS_X, TARGET
from proyecto_1_esp_data.model import construir_pipeline


def entrenar(verbose: bool = True) -> dict:
    """Ajusta, evalúa en validación y producción, y guarda el pipeline."""
    tabla = prepare.construir_tabla_modelo(prepare.cargar_crudo())
    partes = prepare.dividir(tabla)

    pipeline = construir_pipeline()
    pipeline.fit(partes["train"][COLUMNAS_X], partes["train"][TARGET])

    resultados = {}
    for nombre in ("val", "produccion"):
        parte = partes[nombre]
        proba = pipeline.predict_proba(parte[COLUMNAS_X])[:, 1]
        y_pred = pd.Series(
            (proba >= config.UMBRAL_DECISION).astype(int), index=parte.index
        )
        resultados[nombre] = prepare.metricas(parte[TARGET], y_pred)

    config.MODELO_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, config.MODELO_PATH)

    if verbose:
        for nombre, m in resultados.items():
            print(f"{nombre}: {m}")
        print(f"modelo guardado en: {config.MODELO_PATH}")
    return resultados


if __name__ == "__main__":
    entrenar()
