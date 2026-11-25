"""Inferencia de punta a punta: entrena un modelo chico con la muestra, lo guarda,
lo carga con `predict` y verifica que la predicción sea coherente.

No usa el modelo de `models/`: en CI no existe, así que cada prueba entrena el suyo.
"""

from pathlib import Path

import joblib
import pytest

from proyecto_1_esp_data import config, predict
from proyecto_1_esp_data.data import prepare
from proyecto_1_esp_data.features import COLUMNAS_X, TARGET
from proyecto_1_esp_data.model import construir_pipeline

MUESTRA = Path(__file__).parent / "fixtures" / "muestra_beijing.csv"

EJEMPLO = {
    "pm25": 80.0,
    "PM10": 120.0,
    "SO2": 10.0,
    "NO2": 45.0,
    "CO": 900.0,
    "O3": 40.0,
    "TEMP": 5.0,
    "PRES": 1020.0,
    "DEWP": -10.0,
    "RAIN": 0.0,
    "WSPM": 2.5,
    "pm25_lag1": 70.0,
    "pm25_lag2": 65.0,
    "wd": "NW",
    "station": "Aotizhongxin",
    "estacion_ano": "invierno",
}


@pytest.fixture
def modelo_entrenado(tmp_path, monkeypatch):
    """Entrena con la muestra, guarda en una carpeta temporal y apunta `predict` ahí."""
    tabla = prepare.construir_tabla_modelo(prepare.cargar_crudo(MUESTRA))
    pipeline = construir_pipeline().fit(tabla[COLUMNAS_X], tabla[TARGET])

    ruta = tmp_path / "modelo.joblib"
    joblib.dump(pipeline, ruta)
    monkeypatch.setattr(config, "MODELO_PATH", ruta)
    monkeypatch.setattr(predict, "_pipeline", None)  # sin caché de otra prueba
    return ruta


def test_prediccion_de_punta_a_punta(modelo_entrenado):
    resultado = predict.predecir(EJEMPLO)

    assert set(resultado) == {
        "probabilidad_pm25_mala_manana",
        "mala_calidad_manana",
        "umbral_pm25",
    }
    p = resultado["probabilidad_pm25_mala_manana"]
    assert 0.0 <= p <= 1.0
    assert isinstance(resultado["mala_calidad_manana"], bool)
    assert resultado["umbral_pm25"] == config.UMBRAL_PM25


def test_prediccion_acepta_valores_faltantes(modelo_entrenado):
    datos = {**EJEMPLO, "CO": None, "pm25_lag2": None}
    p = predict.predecir(datos)["probabilidad_pm25_mala_manana"]
    assert 0.0 <= p <= 1.0


def test_prediccion_rechaza_columnas_faltantes(modelo_entrenado):
    datos = {k: v for k, v in EJEMPLO.items() if k != "station"}
    with pytest.raises(ValueError, match="station"):
        predict.predecir(datos)


def test_sin_modelo_avisa_que_hay_que_entrenar(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODELO_PATH", tmp_path / "no_existe.joblib")
    monkeypatch.setattr(predict, "_pipeline", None)
    with pytest.raises(FileNotFoundError, match="make train"):
        predict.predecir(EJEMPLO)
