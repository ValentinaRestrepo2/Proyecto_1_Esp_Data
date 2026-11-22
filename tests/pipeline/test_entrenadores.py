"""Entrenadores del pipeline: LightGBM registrado, sin fuga y con predicciones válidas.

No usan Prefect: prueban las funciones de `entrenadores.py` directamente, con la
muestra de `tests/fixtures/` partida por fecha.
"""

from pathlib import Path

import pandas as pd
import pytest

from proyecto_1_esp_data.data import prepare
from proyecto_1_esp_data.pipeline.entrenadores import ENTRENADORES, entrenar_lightgbm

MUESTRA = Path(__file__).parents[1] / "fixtures" / "muestra_beijing.csv"


@pytest.fixture(scope="module")
def partes() -> dict[str, pd.DataFrame]:
    """La muestra (20 días) partida por fecha: 14 días para train y 6 para val."""
    tabla = prepare.construir_tabla_modelo(prepare.cargar_crudo(MUESTRA))
    tabla = tabla.sort_values("fecha").reset_index(drop=True)
    return {"train": tabla.iloc[:14].copy(), "val": tabla.iloc[14:].copy()}


def test_lightgbm_esta_registrado():
    assert set(ENTRENADORES) == {"baseline", "lightgbm"}


def test_lightgbm_predice_ceros_y_unos_alineados(partes):
    candidato = entrenar_lightgbm(partes)
    pred = candidato.predecir(partes["val"])

    assert candidato.nombre == "lightgbm"
    assert pred.index.equals(partes["val"].index)
    assert set(pred.unique()) <= {0.0, 1.0}
    # Las métricas del pipeline se calculan sobre estas predicciones
    assert prepare.metricas(partes["val"]["target"], pred)["n"] == len(partes["val"])


def test_lightgbm_no_mira_validacion(partes):
    """Si cambian los targets de validación, el modelo debe ser exactamente el mismo."""
    alterada = {
        **partes,
        "val": partes["val"].assign(target=1 - partes["val"]["target"]),
    }

    original = entrenar_lightgbm(partes).predecir(partes["val"])
    con_val_cambiada = entrenar_lightgbm(alterada).predecir(alterada["val"])

    pd.testing.assert_series_equal(original, con_val_cambiada)


def test_lightgbm_registra_sus_parametros(partes):
    parametros = entrenar_lightgbm(partes).parametros
    for clave in ("n_estimators", "learning_rate", "random_state", "umbral_decision"):
        assert clave in parametros
