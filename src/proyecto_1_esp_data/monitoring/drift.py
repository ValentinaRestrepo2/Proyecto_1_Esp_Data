"""Reporte de drift con Evidently entre dos ventanas reales de 12 meses.

Compara la ventana de referencia (2015) con la actual (2016), ambas de
`config.py`. Guarda el reporte HTML y un resumen JSON en `reports/`.

Uso:
    uv run python -m proyecto_1_esp_data.monitoring.drift            # genera el reporte
    uv run python -m proyecto_1_esp_data.monitoring.drift --check    # solo verifica

`--check` no escribe archivos y termina con código de salida 1 si hay drift
(0 si no lo hay). Se pueden cambiar las ventanas con `--referencia` y `--actual`:

    # Con drift (2015 contra 2016): sale con código 1
    uv run python -m proyecto_1_esp_data.monitoring.drift --check
    # Sin drift (dos años consecutivos tranquilos): sale con código 0
    uv run python -m proyecto_1_esp_data.monitoring.drift --check \
        --referencia 2013-03-01 2014-02-28 --actual 2014-03-01 2015-02-28

El drift es una alerta para que una persona revise: no dispara reentrenamiento
ni promoción de modelos por sí solo.
"""

from __future__ import annotations

import argparse
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


def resumir(
    resultado,
    referencia: pd.DataFrame,
    actual: pd.DataFrame,
    ventana_ref: tuple[str, str] = config.DRIFT_REFERENCIA,
    ventana_act: tuple[str, str] = config.DRIFT_ACTUAL,
) -> dict:
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
        "referencia": contexto(referencia, *ventana_ref),
        "actual": contexto(actual, *ventana_act),
        "accion": "ALERTA: revisar con una persona (ver docs/politica-de-reentrenamiento.md); "
        "no reentrenar ni promover modelos automáticamente.",
    }


def evaluar(
    tabla: pd.DataFrame,
    ventana_ref: tuple[str, str] = config.DRIFT_REFERENCIA,
    ventana_act: tuple[str, str] = config.DRIFT_ACTUAL,
):
    """Compara dos ventanas y devuelve (resultado de Evidently, resumen)."""
    referencia = ventana(tabla, *ventana_ref)
    actual = ventana(tabla, *ventana_act)
    if referencia.empty or actual.empty:
        raise ValueError("Una de las ventanas de drift no tiene datos")
    resultado = calcular_drift(referencia, actual)
    return resultado, resumir(resultado, referencia, actual, ventana_ref, ventana_act)


def generar_reporte(tabla: pd.DataFrame, salida: Path = config.REPORTES) -> dict:
    """Genera el HTML y el resumen JSON en `salida` y devuelve el resumen."""
    resultado, resumen = evaluar(tabla)
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    resultado.save_html(str(salida / NOMBRE_HTML))
    (salida / NOMBRE_RESUMEN).write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return resumen


def main(argv: list[str] | None = None, tabla: pd.DataFrame | None = None) -> int:
    """Punto de entrada. Devuelve el código de salida (1 = drift con --check)."""
    parser = argparse.ArgumentParser(description="Reporte de drift con Evidently")
    parser.add_argument(
        "--check",
        action="store_true",
        help="solo verificar: sin archivos, exit 1 si hay drift",
    )
    parser.add_argument("--referencia", nargs=2, metavar=("INICIO", "FIN"))
    parser.add_argument("--actual", nargs=2, metavar=("INICIO", "FIN"))
    args = parser.parse_args(argv)

    if tabla is None:
        tabla = prepare.construir_tabla_modelo(prepare.cargar_crudo())
    ventana_ref = tuple(args.referencia) if args.referencia else config.DRIFT_REFERENCIA
    ventana_act = tuple(args.actual) if args.actual else config.DRIFT_ACTUAL

    if args.check:
        _, resumen = evaluar(tabla, ventana_ref, ventana_act)
    else:
        if args.referencia or args.actual:
            parser.error("Sin --check solo se usan las ventanas de config.py")
        resumen = generar_reporte(tabla)
        print(f"Reporte: {config.REPORTES / NOMBRE_HTML}")

    print(
        f"Drift detectado: {resumen['drift_detectado']} "
        f"({len(resumen['columnas_con_drift'])}/{resumen['columnas_evaluadas']} columnas)"
    )
    return 1 if args.check and resumen["drift_detectado"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
