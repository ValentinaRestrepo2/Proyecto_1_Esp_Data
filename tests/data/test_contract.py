"""Pruebas del contrato de datos: uno válido pasa y cada fixture roto se rechaza."""

import pandas as pd
import pytest

from proyecto_1_esp_data import config
from proyecto_1_esp_data.data.contract import ContratoError, validar, validar_o_fallar


def _base(n: int = 40) -> pd.DataFrame:
    """Datos sintéticos mínimos que cumplen el contrato (solo para pruebas)."""
    return pd.DataFrame(
        {
            "No": range(1, n + 1),
            "year": 2014,
            "month": 5,
            "day": [1 + i // 24 for i in range(n)],
            "hour": [i % 24 for i in range(n)],
            "PM2.5": 50.0,
            "PM10": 80.0,
            "SO2": 10.0,
            "NO2": 40.0,
            "CO": 800.0,
            "O3": 60.0,
            "TEMP": 20.0,
            "PRES": 1010.0,
            "DEWP": 5.0,
            "RAIN": 0.0,
            "WSPM": 1.5,
            "wd": "N",
            "station": "Dongsi",
        }
    )


def test_datos_validos_pasan():
    assert validar(_base(), volumen=False) == []
    validar_o_fallar(_base(), volumen=False)


def test_columna_faltante_se_rechaza():
    df = _base().drop(columns=["PM2.5"])
    assert any("Faltan columnas" in p for p in validar(df, volumen=False))


def test_pm_negativo_se_rechaza():
    df = _base()
    df.loc[0, "PM2.5"] = -5.0
    assert any("PM2.5" in p for p in validar(df, volumen=False))


def test_rango_fisico_se_rechaza():
    df = _base()
    df.loc[0, "TEMP"] = 90.0
    df.loc[1, "PRES"] = 500.0
    problemas = validar(df, volumen=False)
    assert any("TEMP" in p for p in problemas)
    assert any("PRES" in p for p in problemas)


def test_punto_de_rocio_sobre_temperatura_se_rechaza():
    df = _base()
    df.loc[0, "DEWP"] = df.loc[0, "TEMP"] + 1
    assert any("DEWP > TEMP" in p for p in validar(df, volumen=False))


def test_punto_de_rocio_igual_a_temperatura_es_valido():
    df = _base()
    df.loc[0, "DEWP"] = df.loc[0, "TEMP"]
    assert validar(df, volumen=False) == []


def test_hora_fuera_de_rango_se_rechaza():
    df = _base()
    df.loc[0, "hour"] = 24
    assert any("hour" in p for p in validar(df, volumen=False))


def test_filas_duplicadas_se_rechazan():
    df = pd.concat([_base(), _base().iloc[[0]]], ignore_index=True)
    assert any("duplicadas" in p for p in validar(df, volumen=False))


def test_pm10_menor_que_pm25_en_exceso_se_rechaza():
    df = _base()
    df["PM10"] = 10.0  # PM10 < PM2.5 en el 100 % de las filas
    assert any("PM10 < PM2.5" in p for p in validar(df, volumen=False))


def test_pm10_menor_que_pm25_dentro_de_tolerancia_pasa():
    df = _base(100)
    df.loc[0, "PM10"] = 10.0  # 1 % de las filas, bajo la tolerancia
    assert validar(df, volumen=False) == []


def test_direccion_de_viento_invalida_se_rechaza():
    df = _base()
    df.loc[0, "wd"] = "XYZ"
    assert any("wd" in p for p in validar(df, volumen=False))


def test_exceso_de_nulos_se_rechaza():
    df = _base()
    df.loc[: len(df) // 2, "O3"] = None
    assert any("O3" in p and "nulos" in p for p in validar(df, volumen=False))


def test_volumen_incorrecto_se_rechaza():
    # 1 estación y 40 filas: no cumple 12 estaciones x 35.064 filas
    problemas = validar(_base(), volumen=True)
    assert any("Estaciones" in p for p in problemas)
    assert any(str(config.FILAS_POR_ESTACION) in p for p in problemas)


def test_validar_o_fallar_lanza_error():
    df = _base()
    df.loc[0, "PM10"] = -1.0
    with pytest.raises(ContratoError):
        validar_o_fallar(df, volumen=False)
