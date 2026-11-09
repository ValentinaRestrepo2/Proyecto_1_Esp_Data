"""Contrato de datos procesados: una tabla bien construida pasa y cada error se rechaza."""

import numpy as np
import pandas as pd
import pytest

from proyecto_1_esp_data import config
from proyecto_1_esp_data.data import prepare
from proyecto_1_esp_data.data.contract import (
    ContratoError,
    validar_procesado,
    validar_procesado_o_fallar,
)


def _crudo(dias: int = 10, estacion: str = "A") -> pd.DataFrame:
    """Datos horarios sintéticos y válidos; el PM2.5 sube día a día."""
    filas = []
    for d in range(dias):
        f = pd.Timestamp("2014-01-01") + pd.Timedelta(days=d)
        filas.append(
            pd.DataFrame(
                {
                    "year": f.year,
                    "month": f.month,
                    "day": f.day,
                    "hour": range(24),
                    "PM2.5": 30.0 + 10.0 * d,
                    "PM10": 200.0,
                    "SO2": 5.0,
                    "NO2": 30.0,
                    "CO": 500.0,
                    "O3": 40.0,
                    "TEMP": 10.0,
                    "PRES": 1010.0,
                    "DEWP": 0.0,
                    "RAIN": 0.0,
                    "WSPM": 1.0,
                    "wd": "N",
                    "station": estacion,
                }
            )
        )
    return pd.concat(filas, ignore_index=True)


@pytest.fixture
def tabla() -> pd.DataFrame:
    return prepare.construir_tabla_modelo(_crudo())


def test_tabla_bien_construida_pasa(tabla):
    assert validar_procesado(tabla) == []
    validar_procesado_o_fallar(tabla)


def test_hay_filas_con_target_de_cada_clase():
    # PM2.5 de 30 a 120: cruza el umbral de 75, así que hay ceros y unos
    t = prepare.construir_tabla_modelo(_crudo(dias=10))
    assert set(t["target"]) == {0, 1}


def test_columna_faltante_se_rechaza(tabla):
    assert any(
        "Faltan columnas" in p
        for p in validar_procesado(tabla.drop(columns=["target"]))
    )


def test_tabla_vacia_se_rechaza(tabla):
    assert validar_procesado(tabla.iloc[0:0])


def test_target_fuera_de_0_y_1_se_rechaza(tabla):
    tabla.loc[0, "target"] = 2
    assert any("target debe ser 0 o 1" in p for p in validar_procesado(tabla))


def test_target_incoherente_con_el_pm25_de_manana_se_rechaza(tabla):
    tabla.loc[0, "target"] = 1 - tabla.loc[0, "target"]
    assert any("target no coincide" in p for p in validar_procesado(tabla))


def test_rezago_con_informacion_de_hoy_se_rechaza(tabla):
    # Fuga típica: el "rezago" de ayer en realidad es el valor de hoy
    tabla["pm25_lag1"] = tabla["pm25"]
    assert any("pm25_lag1" in p for p in validar_procesado(tabla))


def test_fecha_objetivo_que_no_es_el_dia_siguiente_se_rechaza(tabla):
    tabla.loc[0, "fecha_objetivo"] = tabla.loc[0, "fecha"] + pd.Timedelta(days=2)
    assert any("fecha_objetivo" in p for p in validar_procesado(tabla))


def test_filas_duplicadas_se_rechazan(tabla):
    duplicada = pd.concat([tabla, tabla.iloc[[0]]], ignore_index=True)
    assert any("duplicadas" in p for p in validar_procesado(duplicada))


def test_dia_con_pocas_horas_y_pm25_se_rechaza(tabla):
    tabla.loc[0, "horas_pm25"] = config.HORAS_VALIDAS_MIN_POR_DIA - 1
    assert any("menos de" in p for p in validar_procesado(tabla))


def test_pm25_fuera_de_rango_se_rechaza(tabla):
    tabla.loc[0, "pm25"] = 5000.0
    assert any("pm25 fuera de" in p for p in validar_procesado(tabla))


def test_estacion_del_ano_incoherente_con_el_mes_se_rechaza(tabla):
    tabla["estacion_ano"] = "verano"  # enero es invierno
    assert any("estacion_ano" in p for p in validar_procesado(tabla))


def test_validar_procesado_o_fallar_lanza_error(tabla):
    tabla.loc[0, "target"] = np.nan
    with pytest.raises(ContratoError):
        validar_procesado_o_fallar(tabla)
