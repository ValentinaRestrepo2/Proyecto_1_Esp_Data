"""Inferencia de punta a punta: entrena un modelo chico con la muestra, lo guarda,
lo carga con `predict` y verifica que la predicción sea coherente.

No usa el modelo de `models/`: en CI no existe, así que cada prueba entrena el suyo.
"""

from pathlib import Path

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
def modelo_entrenado(monkeypatch):
    """Entrena con la muestra y lo deja en memoria como si fuera el modelo vigente."""
    tabla = prepare.construir_tabla_modelo(prepare.cargar_crudo(MUESTRA))
    pipeline = construir_pipeline().fit(tabla[COLUMNAS_X], tabla[TARGET])
    monkeypatch.setattr(predict, "_pipeline", pipeline)
    monkeypatch.setattr(predict, "_version", "1")
    return pipeline


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


def test_sin_modelo_vigente_avisa_que_hay_que_entrenar_y_promover(
    tmp_path, monkeypatch
):
    """Con un registro vacío (sin alias champion) no hay nada que servir."""
    monkeypatch.setenv(
        "MLFLOW_TRACKING_URI", f"sqlite:///{(tmp_path / 'vacio.db').as_posix()}"
    )
    monkeypatch.setattr(predict, "_pipeline", None)
    monkeypatch.setattr(predict, "_version", None)
    with pytest.raises(FileNotFoundError, match="make train.*make promote"):
        predict.predecir(EJEMPLO)
    assert predict.modelo_disponible() is False
