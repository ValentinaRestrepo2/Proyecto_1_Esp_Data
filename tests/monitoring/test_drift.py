"""Pruebas del reporte de drift: sin cambio no hay alerta, con cambio sí."""

import json

import numpy as np
import pandas as pd
import pytest

from proyecto_1_esp_data import config
from proyecto_1_esp_data.monitoring import drift

N = 600


def _tabla(
    inicio: str, escala: float = 1.0, semilla: int = config.SEMILLA
) -> pd.DataFrame:
    """Tabla sintética con las columnas que usa el monitoreo."""
    rng = np.random.default_rng(semilla)
    fechas = pd.date_range(inicio, periods=N, freq="D")
    tabla = pd.DataFrame({"fecha": fechas})
    for col in config.DRIFT_COLUMNAS_NUM:
        tabla[col] = rng.gamma(shape=2.0, scale=20.0, size=N) * escala
    tabla["wd"] = rng.choice(config.DIRECCIONES_VIENTO, size=N)
    tabla["station"] = rng.choice(["A", "B", "C"], size=N)
    tabla["estacion_ano"] = rng.choice(["invierno", "verano"], size=N)
    tabla["target"] = rng.integers(0, 2, size=N)
    tabla["hoy_supera"] = rng.integers(0, 2, size=N).astype(float)
    return tabla


@pytest.fixture(scope="module")
def sin_cambio():
    ref, act = _tabla("2015-01-01", semilla=1), _tabla("2016-01-01", semilla=2)
    resultado = drift.calcular_drift(ref, act)
    return drift.resumir(resultado, ref, act)


@pytest.fixture(scope="module")
def con_cambio():
    ref, act = (
        _tabla("2015-01-01", semilla=1),
        _tabla("2016-01-01", escala=3.0, semilla=2),
    )
    resultado = drift.calcular_drift(ref, act)
    return drift.resumir(resultado, ref, act)


def test_misma_distribucion_no_dispara_alerta(sin_cambio):
    assert sin_cambio["drift_detectado"] is False
    # El ruido de muestreo puede marcar alguna columna suelta, nunca la mayoría
    assert sin_cambio["proporcion_con_drift"] < config.DRIFT_UMBRAL_COMPARTIDO


def test_distribucion_distinta_dispara_alerta(con_cambio):
    assert con_cambio["drift_detectado"] is True
    # Las 13 columnas numéricas se triplicaron: todas deben marcarse
    assert set(config.DRIFT_COLUMNAS_NUM) <= set(con_cambio["columnas_con_drift"])


def test_el_resumen_incluye_umbrales_y_contexto(con_cambio):
    assert con_cambio["umbral_columna"] == config.DRIFT_UMBRAL_COLUMNA
    assert con_cambio["umbral_compartido"] == config.DRIFT_UMBRAL_COMPARTIDO
    assert con_cambio["columnas_evaluadas"] == len(drift.COLUMNAS)
    assert con_cambio["referencia"]["inicio"] == config.DRIFT_REFERENCIA[0]
    assert con_cambio["actual"]["fin"] == config.DRIFT_ACTUAL[1]
    assert "no reentrenar" in con_cambio["accion"]


def test_ventana_incluye_los_extremos():
    tabla = pd.DataFrame({"fecha": pd.date_range("2015-12-30", "2016-01-03", freq="D")})
    v = drift.ventana(tabla, "2015-12-31", "2016-01-02")
    assert v["fecha"].min() == pd.Timestamp("2015-12-31")
    assert v["fecha"].max() == pd.Timestamp("2016-01-02")
    assert len(v) == 3


def test_generar_reporte_escribe_html_y_json(tmp_path, monkeypatch):
    # Ventanas sintéticas dentro de las fechas configuradas
    ref = _tabla(config.DRIFT_REFERENCIA[0], semilla=1)
    act = _tabla(config.DRIFT_ACTUAL[0], escala=3.0, semilla=2)
    tabla = pd.concat([ref, act], ignore_index=True)

    resumen = drift.generar_reporte(tabla, salida=tmp_path)

    html = tmp_path / drift.NOMBRE_HTML
    assert html.exists() and html.stat().st_size > 10_000
    guardado = json.loads((tmp_path / drift.NOMBRE_RESUMEN).read_text(encoding="utf-8"))
    assert guardado["drift_detectado"] == resumen["drift_detectado"] is True


def test_ventana_vacia_se_rechaza(tmp_path):
    solo_ref = _tabla(config.DRIFT_REFERENCIA[0]).head(100)  # no llega a 2016
    with pytest.raises(ValueError):
        drift.generar_reporte(solo_ref, salida=tmp_path)
