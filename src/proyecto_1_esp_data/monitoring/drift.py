"""Reporte de drift con Evidently entre dos ventanas reales de 12 meses.

Compara la ventana de referencia (2015) con la actual (2016), ambas de
`config.py`. Guarda el reporte HTML y un resumen JSON en `reports/`.

Uso:
    uv run python -m proyecto_1_esp_data.monitoring.drift

El drift es una alerta para que una persona revise: no dispara reentrenamiento
ni promoción de modelos por sí solo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from evidently import DataDefinition, Dataset, Report
from evidently.presets import DataDriftPreset

from proyecto_1_esp_data import config
from proyecto_1_esp_data.data import prepare

COLUMNAS = config.DRIFT_COLUMNAS_NUM + config.DRIFT_COLUMNAS_CAT
NOMBRE_HTML = "drift_referencia_vs_actual.html"
NOMBRE_RESUMEN = "drift_resumen.json"


def ventana(tabla: pd.DataFrame, inicio: str, fin: str) -> pd.DataFrame:
    """Filas con fecha entre `inicio` y `fin` (ambos incluidos)."""
    return tabla[(tabla["fecha"] >= inicio) & (tabla["fecha"] <= fin)]


def calcular_drift(referencia: pd.DataFrame, actual: pd.DataFrame):
    """Corre el reporte de Evidently y devuelve el resultado (snapshot)."""
    definicion = DataDefinition(
        numerical_columns=config.DRIFT_COLUMNAS_NUM,
        categorical_columns=config.DRIFT_COLUMNAS_CAT,
    )
    ref = Dataset.from_pandas(referencia[COLUMNAS], data_definition=definicion)
    act = Dataset.from_pandas(actual[COLUMNAS], data_definition=definicion)
    reporte = Report(
        [
            DataDriftPreset(
                drift_share=config.DRIFT_UMBRAL_COMPARTIDO,
                # Métodos fijos: si no, Evidently cambia de prueba según el tamaño
                # de la muestra (K-S con p-valor bajo 1.000 filas), y el umbral
                # dejaría de significar lo mismo.
                num_method="wasserstein",
                cat_method="jensenshannon",
                num_threshold=config.DRIFT_UMBRAL_COLUMNA,
                cat_threshold=config.DRIFT_UMBRAL_COLUMNA,
            )
        ]
    )
    return reporte.run(act, ref)


def _por_columna(resultado) -> dict[str, float]:
    """Distancia de drift por columna, tomada del resultado de Evidently."""
    columnas = {}
    for metrica in resultado.dict()["metrics"]:
        columna = metrica["config"].get("column")
        if columna is not None:
            columnas[columna] = float(metrica["value"])
    return columnas


def resumir(resultado, referencia: pd.DataFrame, actual: pd.DataFrame) -> dict:
    """Resumen legible del drift: decisión, columnas afectadas y contexto."""
    distancias = _por_columna(resultado)
    con_drift = sorted(
        c for c, v in distancias.items() if v >= config.DRIFT_UMBRAL_COLUMNA
    )
    proporcion = len(con_drift) / len(distancias)

    def contexto(tabla: pd.DataFrame, inicio: str, fin: str) -> dict:
        m = prepare.metricas(tabla["target"], prepare.baseline_persistencia(tabla))
        return {
            "inicio": inicio,
            "fin": fin,
            "filas": len(tabla),
            "porcentaje_dias_sobre_umbral": round(
                float(tabla["target"].mean()) * 100, 1
            ),
            "linea_base_sensibilidad": round(m["sensibilidad"], 3),
        }

    return {
        "drift_detectado": proporcion >= config.DRIFT_UMBRAL_COMPARTIDO,
        "columnas_evaluadas": len(distancias),
        "columnas_con_drift": con_drift,
        "proporcion_con_drift": round(proporcion, 3),
        "umbral_columna": config.DRIFT_UMBRAL_COLUMNA,
        "umbral_compartido": config.DRIFT_UMBRAL_COMPARTIDO,
        "distancias": {c: round(v, 4) for c, v in sorted(distancias.items())},
        "referencia": contexto(referencia, *config.DRIFT_REFERENCIA),
        "actual": contexto(actual, *config.DRIFT_ACTUAL),
        "accion": "ALERTA: revisar con una persona (ver docs/politica-de-reentrenamiento.md); "
        "no reentrenar ni promover modelos automáticamente.",
    }


def generar_reporte(tabla: pd.DataFrame, salida: Path = config.REPORTES) -> dict:
    """Genera el HTML y el resumen JSON en `salida` y devuelve el resumen."""
    referencia = ventana(tabla, *config.DRIFT_REFERENCIA)
    actual = ventana(tabla, *config.DRIFT_ACTUAL)
    if referencia.empty or actual.empty:
        raise ValueError("Una de las ventanas de drift no tiene datos")

    resultado = calcular_drift(referencia, actual)
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    resultado.save_html(str(salida / NOMBRE_HTML))
    resumen = resumir(resultado, referencia, actual)
    (salida / NOMBRE_RESUMEN).write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return resumen


def main() -> None:
    tabla = prepare.construir_tabla_modelo(prepare.cargar_crudo())
    resumen = generar_reporte(tabla)
    print(
        f"Drift detectado: {resumen['drift_detectado']} "
        f"({len(resumen['columnas_con_drift'])}/{resumen['columnas_evaluadas']} columnas)"
    )
    print(f"Reporte: {config.REPORTES / NOMBRE_HTML}")


if __name__ == "__main__":
    main()
