"""Se prueba con TestClient (sin levantar el servidor)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api_fastapi import MENSAJE_SIN_MODELO, app
from proyecto_1_esp_data import predict
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
def con_modelo(monkeypatch):
    """Se entrena un modelo con la muestra y se deja en memoria como el vigente."""
    tabla = prepare.construir_tabla_modelo(prepare.cargar_crudo(MUESTRA))
    pipeline = construir_pipeline().fit(tabla[COLUMNAS_X], tabla[TARGET])
    monkeypatch.setattr(predict, "_pipeline", pipeline)
    monkeypatch.setattr(predict, "_version", "7")
    return TestClient(app)


@pytest.fixture
def sin_modelo(tmp_path, monkeypatch):
    """Registro vacío (sin alias champion), para probar el error 503."""
    monkeypatch.setenv(
        "MLFLOW_TRACKING_URI", f"sqlite:///{(tmp_path / 'vacio.db').as_posix()}"
    )
    monkeypatch.setattr(predict, "_pipeline", None)
    monkeypatch.setattr(predict, "_version", None)
    return TestClient(app)


def test_health_con_modelo(con_modelo):
    r = con_modelo.get("/health")
    assert r.status_code == 200
    assert r.json() == {
        "estado": "ok",
        "modelo_disponible": True,
        "version_modelo": "7",
    }


def test_health_sin_modelo_lo_reporta(sin_modelo):
    r = sin_modelo.get("/health")
    assert r.status_code == 200
    assert r.json()["modelo_disponible"] is False
    assert r.json()["version_modelo"] is None


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


def test_predict_sin_modelo_responde_503_con_mensaje_fijo(sin_modelo):
    r = sin_modelo.post("/predict", json=EJEMPLO)
    assert r.status_code == 503
    # Mensaje fijo: no se devuelve str(e) (podría filtrar rutas o detalles internos)
    assert r.json()["detail"] == MENSAJE_SIN_MODELO
