"""Fixtures compartidas.

Crear una base de MLflow desde cero ejecuta todas sus migraciones (varios segundos en
Linux y bastante más en Windows). Antes cada prueba hacía eso con su propia base y la
suite entera tardaba más de 8 minutos en Windows. Ahora la base se migra UNA vez por
sesión de pruebas y cada prueba recibe una copia: el aislamiento es el mismo (cada
prueba tiene su registro propio y vacío), pero se paga el costo una sola vez.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_MIGRAR = (
    "import mlflow, sys;"
    "mlflow.MlflowClient(tracking_uri=sys.argv[1]).search_experiments()"
)


def _copiar_base(origen: Path, destino: Path) -> None:
    """Copia una base SQLite con su API de respaldo: es segura aunque haya conexiones abiertas."""
    with sqlite3.connect(origen) as a, sqlite3.connect(destino) as b:
        a.backup(b)
    # `with` confirma pero no cierra la conexión: se cierran para liberar los archivos (Windows).
    a.close()
    b.close()


@pytest.fixture(scope="session")
def copiar_base():
    """Devuelve la función que copia una base SQLite (para usarla desde otras fixtures)."""
    return _copiar_base


@pytest.fixture(scope="session")
def base_mlflow_migrada(tmp_path_factory):
    """Base SQLite de MLflow ya migrada y vacía (sin experimentos ni modelos)."""
    ruta = tmp_path_factory.mktemp("plantilla_mlflow") / "mlflow.db"
    # En un proceso aparte, para que el archivo quede cerrado antes de copiarlo.
    subprocess.run(
        [sys.executable, "-c", _MIGRAR, f"sqlite:///{ruta.as_posix()}"],
        check=True,
        capture_output=True,
    )
    return ruta


@pytest.fixture
def registro_aislado(base_mlflow_migrada, tmp_path, monkeypatch):
    """Registro de MLflow vacío y propio de la prueba; los artefactos van a su carpeta."""
    destino = tmp_path / "mlflow.db"
    _copiar_base(base_mlflow_migrada, destino)
    monkeypatch.chdir(tmp_path)  # los artefactos de MLflow van a ./mlruns
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{destino.as_posix()}")
    return tmp_path
