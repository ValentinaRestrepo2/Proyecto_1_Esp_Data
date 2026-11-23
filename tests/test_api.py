"""Se prueba con TestClient (sin levantar el servidor)."""

from pathlib import Path

import joblib
import pytest
from fastapi.testclient import TestClient

from app.api_fastapi import app
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
def con_modelo(tmp_path, monkeypatch):
    """Se entrena un modelo con la muestra, se guarda en una carpeta temporal y se usa."""
    tabla = prepare.construir_tabla_modelo(prepare.cargar_crudo(MUESTRA))
    pipeline = construir_pipeline().fit(tabla[COLUMNAS_X], tabla[TARGET])
    ruta = tmp_path / "modelo.joblib"
    joblib.dump(pipeline, ruta)
    monkeypatch.setattr(config, "MODELO_PATH", ruta)
    monkeypatch.setattr(predict, "_pipeline", None)
    return TestClient(app)


@pytest.fixture
def sin_modelo(tmp_path, monkeypatch):
    """Apunta a una ruta donde no hay modelo, para probar el error 503."""
    monkeypatch.setattr(config, "MODELO_PATH", tmp_path / "no_existe.joblib")
    monkeypatch.setattr(predict, "_pipeline", None)
    return TestClient(app)


def test_health_con_modelo(con_modelo):
    r = con_modelo.get("/health")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok", "modelo_disponible": True}


def test_health_sin_modelo_lo_reporta(sin_modelo):
    r = sin_modelo.get("/health")
    assert r.status_code == 200
    assert r.json()["modelo_disponible"] is False


def test_predict_responde_200_con_el_contrato(con_modelo):
    r = con_modelo.post("/predict", json=EJEMPLO)
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) == {
        "probabilidad_pm25_mala_manana",
        "mala_calidad_manana",
        "umbral_pm25",
    }
    assert 0.0 <= cuerpo["probabilidad_pm25_mala_manana"] <= 1.0
    assert isinstance(cuerpo["mala_calidad_manana"], bool)


def test_predict_acepta_valores_nulos(con_modelo):
    r = con_modelo.post("/predict", json={**EJEMPLO, "CO": None})
    assert r.status_code == 200


def test_predict_rechaza_campo_obligatorio_faltante(con_modelo):
    cuerpo = {k: v for k, v in EJEMPLO.items() if k != "station"}
    r = con_modelo.post("/predict", json=cuerpo)
    assert r.status_code == 422


def test_predict_sin_modelo_responde_503(sin_modelo):
    r = sin_modelo.post("/predict", json=EJEMPLO)
    assert r.status_code == 503
    assert "make train" in r.json()["detail"]
