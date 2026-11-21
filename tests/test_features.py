"""Pipeline de features: columnas de entrada y preprocesador, con la muestra real."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from proyecto_1_esp_data.data import prepare
from proyecto_1_esp_data.features import (
    CATEGORICAS,
    COLUMNAS_X,
    NUMERICAS,
    TARGET,
    construir_preprocesador,
)

MUESTRA = Path(__file__).parent / "fixtures" / "muestra_beijing.csv"


@pytest.fixture(scope="module")
def tabla():
    """Tabla diaria con target y features, construida desde la muestra horaria."""
    return prepare.construir_tabla_modelo(prepare.cargar_crudo(MUESTRA))


def test_la_tabla_tiene_todas_las_columnas_de_entrada(tabla):
    faltantes = [c for c in [*COLUMNAS_X, TARGET] if c not in tabla.columns]
    assert faltantes == []


def test_las_entradas_no_incluyen_informacion_de_manana():
    # Si el target o datos de mañana entraran como feature, habría fuga de datos
    for columna in ("target", "pm25_manana", "fecha_objetivo", "hoy_supera"):
        assert columna not in COLUMNAS_X


def test_preprocesador_devuelve_matriz_completa_sin_nulos(tabla):
    preprocesador = construir_preprocesador()
    x = preprocesador.fit_transform(tabla[COLUMNAS_X])

    assert x.shape[0] == len(tabla)
    # Una columna por numérica, más una por cada categoría vista en el ajuste
    categorias = sum(tabla[c].nunique() for c in CATEGORICAS)
    assert x.shape[1] == len(NUMERICAS) + categorias
    # La muestra tiene nulos (pm25_lag1 del primer día): el imputador los rellena
    assert tabla[NUMERICAS].isna().any().any()
    assert not np.isnan(x).any()


def test_preprocesador_tolera_categorias_nuevas(tabla):
    preprocesador = construir_preprocesador().fit(tabla[COLUMNAS_X])
    nueva = tabla[COLUMNAS_X].head(1).copy()
    nueva["station"] = "EstacionQueNoExiste"
    nueva["wd"] = None

    x = preprocesador.transform(nueva)

    assert x.shape[0] == 1
    assert not np.isnan(x).any()


def test_preprocesador_no_modifica_los_datos_de_entrada(tabla):
    entrada = tabla[COLUMNAS_X].copy()
    construir_preprocesador().fit_transform(entrada)
    pd.testing.assert_frame_equal(entrada, tabla[COLUMNAS_X])
