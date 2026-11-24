"""Registro de experimentos y modelos con MLflow (backend SQLite local, sin servidor).

Reúne lo que comparten el entrenamiento, la compuerta de promoción y la inferencia:
cómo conectarse al registro, cómo encontrar una versión por alias y cómo leer las
métricas de una corrida. Así los tres hablan del mismo registro con las mismas reglas.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import mlflow
from mlflow import MlflowClient
from mlflow.entities.model_registry import ModelVersion
from mlflow.exceptions import MlflowException

from proyecto_1_esp_data import config

PARTICIONES = ("val", "produccion")
METRICAS = ("sensibilidad", "precision", "f1")
PREFIJO_LINEA_BASE = "linea_base_"


def cliente() -> MlflowClient:
    """Cliente apuntando al registro del proyecto (o al de MLFLOW_TRACKING_URI)."""
    uri = os.environ.get("MLFLOW_TRACKING_URI", config.MLFLOW_TRACKING_URI)
    mlflow.set_tracking_uri(uri)
    mlflow.set_registry_uri(uri)
    return MlflowClient()


def huella_archivo(ruta: str | Path) -> str:
    """SHA-256 del archivo: identifica los datos exactos con que se entrenó."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def version_por_alias(client: MlflowClient, alias: str) -> ModelVersion | None:
    """La versión del modelo registrado que tiene ese alias, o None si no existe."""
    try:
        return client.get_model_version_by_alias(config.MODELO_REGISTRADO, alias)
    except MlflowException:
        return None


def nombres_de_metricas(prefijo: str = "") -> list[str]:
    return [f"{prefijo}{p}_{m}" for p in PARTICIONES for m in METRICAS]


def leer_metricas(metricas_de_la_corrida: dict, prefijo: str = "") -> dict:
    """De las métricas planas de MLflow a {"val": {...}, "produccion": {...}}."""
    return {
        p: {m: float(metricas_de_la_corrida[f"{prefijo}{p}_{m}"]) for m in METRICAS}
        for p in PARTICIONES
    }


def metricas_de_version(client: MlflowClient, version: ModelVersion) -> dict:
    """Métricas del modelo y de la línea base con que se entrenó esa versión."""
    plano = client.get_run(version.run_id).data.metrics
    return {
        "modelo": leer_metricas(plano),
        "linea_base": leer_metricas(plano, PREFIJO_LINEA_BASE),
    }
