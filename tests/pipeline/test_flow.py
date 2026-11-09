"""Pipeline de Prefect: corre de punta a punta, reintenta bien, cachea y no promueve."""

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests

# Prefect lee su configuración al importarse: la base temporal evita tocar la del usuario
_HOME = tempfile.mkdtemp(prefix="prefect_test_")
os.environ.setdefault("PREFECT_HOME", _HOME)
os.environ.setdefault("PREFECT_LOGGING_LEVEL", "ERROR")

from prefect.schedules import Cron
from prefect.testing.utilities import prefect_test_harness

from proyecto_1_esp_data import config
from proyecto_1_esp_data.pipeline import flow as pipeline


def _csv_sintetico(ruta: Path) -> Path:
    """Dos estaciones, 2013-03-01 a 2017-02-28: cubre train, val, producción y drift."""
    rng = np.random.default_rng(config.SEMILLA)
    horas = pd.date_range("2013-03-01", "2017-02-28 23:00", freq="h")
    partes = []
    for estacion in ("A", "B"):
        n = len(horas)
        pm25 = rng.gamma(2.0, 35.0, n).clip(1, 600)
        temp = rng.uniform(-5, 30, n)
        partes.append(
            pd.DataFrame(
                {
                    "year": horas.year,
                    "month": horas.month,
                    "day": horas.day,
                    "hour": horas.hour,
                    "PM2.5": pm25,
                    "PM10": pm25 + 20,
                    "SO2": rng.uniform(1, 40, n),
                    "NO2": rng.uniform(5, 100, n),
                    "CO": rng.uniform(200, 3000, n),
                    "O3": rng.uniform(1, 150, n),
                    "TEMP": temp,
                    "PRES": rng.uniform(1000, 1030, n),
                    "DEWP": temp - rng.uniform(0, 10, n),
                    "RAIN": 0.0,
                    "WSPM": rng.uniform(0, 8, n),
                    "wd": rng.choice(["N", "NE", "E", "S", "SW", "W"], n),
                    "station": estacion,
                }
            )
        )
    df = pd.concat(partes, ignore_index=True)
    df.insert(0, "No", range(1, len(df) + 1))
    df.to_csv(ruta, index=False)
    return ruta


@pytest.fixture(scope="module", autouse=True)
def servidor_prefect():
    with prefect_test_harness():
        yield
    shutil.rmtree(_HOME, ignore_errors=True)


@pytest.fixture(scope="module")
def csv(tmp_path_factory) -> Path:
    return _csv_sintetico(tmp_path_factory.mktemp("datos") / "calidad_aire_beijing.csv")


def _correr(csv: Path, salida: Path) -> dict:
    return pipeline.flujo_calidad_aire(
        ruta_csv=str(csv),
        salida=str(salida),
        validar_volumen=False,
        descargar_si_falta=False,
    )


def test_flujo_completo_registra_candidato_sin_promoverlo(csv, tmp_path):
    resultado = _correr(csv, tmp_path / "reportes")
    registro = json.loads((tmp_path / "reportes" / "candidato.json").read_text())

    assert registro["promovido"] is False
    assert resultado["registro"]["promovido"] is False
    assert registro["candidato"] == "baseline_persistencia"
    assert registro["semilla"] == config.SEMILLA
    assert set(registro["metricas"]["modelo"]) == {"val", "produccion"}
    assert (tmp_path / "reportes" / "drift_resumen.json").exists()
    assert (tmp_path / "reportes" / "drift_referencia_vs_actual.html").exists()


def test_segunda_ejecucion_usa_el_cache(csv, tmp_path, monkeypatch):
    # Sal nueva en cada corrida de las pruebas: la primera ejecución nunca encuentra caché
    monkeypatch.setenv("PIPELINE_CACHE_SALT", uuid.uuid4().hex)
    primera = _correr(csv, tmp_path / "a")["duracion_s"]
    segunda = _correr(csv, tmp_path / "b")["duracion_s"]
    assert segunda < primera


def test_datos_distintos_invalidan_el_cache(csv, tmp_path):
    otro = tmp_path / "calidad_aire_beijing.csv"
    df = pd.read_csv(csv)
    df.loc[0, "SO2"] += 1.0
    df.to_csv(otro, index=False)
    assert pipeline.huella_datos(otro) != pipeline.huella_datos(csv)


def test_modelo_desconocido_falla(csv, tmp_path):
    with pytest.raises(ValueError, match="Modelo desconocido"):
        pipeline.flujo_calidad_aire(
            modelo="no-existe",
            ruta_csv=str(csv),
            salida=str(tmp_path),
            validar_volumen=False,
        )


def test_datos_rotos_detienen_el_flujo(csv, tmp_path):
    roto = tmp_path / "calidad_aire_beijing.csv"
    df = pd.read_csv(csv)
    df.loc[0, "PM2.5"] = 5000  # fuera de rango físico
    df.to_csv(roto, index=False)
    with pytest.raises(Exception, match="fuera de"):
        pipeline.flujo_calidad_aire(
            ruta_csv=str(roto),
            salida=str(tmp_path / "r"),
            validar_volumen=False,
            descargar_si_falta=False,
        )
    assert not (tmp_path / "r" / "candidato.json").exists()


def test_descarga_reintenta_errores_de_red(tmp_path, monkeypatch):
    llamadas = []

    def descargar(destino):
        llamadas.append(1)
        if len(llamadas) < 3:
            raise requests.ConnectionError("sin red")
        return Path(destino) / "calidad_aire_beijing.csv"

    monkeypatch.setattr(pipeline.download, "descargar", descargar)
    tarea = pipeline.asegurar_datos.with_options(retry_delay_seconds=0)
    ruta = tarea(str(tmp_path / "calidad_aire_beijing.csv"), True)
    assert len(llamadas) == 3
    assert ruta.endswith("calidad_aire_beijing.csv")


def test_descarga_no_reintenta_errores_que_no_son_de_red(tmp_path, monkeypatch):
    llamadas = []

    def descargar(destino):
        llamadas.append(1)
        raise ValueError("El ZIP cambió")

    monkeypatch.setattr(pipeline.download, "descargar", descargar)
    tarea = pipeline.asegurar_datos.with_options(retry_delay_seconds=0)
    with pytest.raises(ValueError, match="El ZIP cambió"):
        tarea(str(tmp_path / "calidad_aire_beijing.csv"), True)
    assert len(llamadas) == 1


def test_deployment_tiene_schedule_trimestral():
    despliegue = pipeline.flujo_calidad_aire.to_deployment(
        name=pipeline.NOMBRE_DEPLOYMENT,
        schedule=Cron(config.PIPELINE_CRON, timezone=config.PIPELINE_ZONA_HORARIA),
    )
    cron = despliegue.schedules[0].schedule
    assert cron.cron == config.PIPELINE_CRON
    assert cron.timezone == config.PIPELINE_ZONA_HORARIA
