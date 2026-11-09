"""Diagnóstico rápido del entorno: `make smoke`.

Sale con código 1 y lista todo lo que falta, para que quien clone el repositorio
sepa qué arreglar sin tener que adivinar. No entrena nada ni escribe archivos.

Uso:
    uv run python -m proyecto_1_esp_data.smoke
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import sys
from pathlib import Path

import pandas as pd

from proyecto_1_esp_data import config
from proyecto_1_esp_data.data.contract import validar

PYTHON_MINIMO = (3, 12)
LIBRERIAS = ["pandas", "numpy", "sklearn", "lightgbm", "evidently", "fastapi"]


def _entorno() -> list[str]:
    problemas = []
    if sys.version_info < PYTHON_MINIMO:
        actual = ".".join(map(str, sys.version_info[:3]))
        problemas.append(f"Python {actual}: se requiere 3.12 o superior")
    for nombre in LIBRERIAS:
        if importlib.util.find_spec(nombre) is None:
            problemas.append(f"Falta la librería {nombre}: corre `make setup`")
    # Evidently 0.7.x no se importa con pandas 3 (ver docs/adr/001-python-312.md)
    if int(importlib.metadata.version("pandas").split(".")[0]) >= 3:
        problemas.append("pandas >= 3 rompe Evidently: se requiere pandas < 3")
    return problemas


def _archivos(raiz: Path) -> list[str]:
    problemas = []
    if not (raiz / "uv.lock").exists():
        problemas.append("Falta uv.lock")
    if not (raiz / config.METADATA).exists():
        problemas.append(f"Falta {config.METADATA}: corre `make data`")
    if not (raiz / config.CSV_CRUDO).exists():
        problemas.append(f"Falta {config.CSV_CRUDO}: corre `make data`")
    return problemas


def _particiones() -> list[str]:
    """Las fechas fijas del split deben ir en orden y sin solaparse."""
    fechas = [
        config.TRAIN_INICIO,
        config.TRAIN_FIN,
        config.VAL_INICIO,
        config.VAL_FIN,
        config.PRODUCCION_INICIO,
        config.PRODUCCION_FIN,
    ]
    ordenadas = [pd.Timestamp(f) for f in fechas]
    if ordenadas != sorted(ordenadas) or len(set(ordenadas)) != len(ordenadas):
        return ["Las fechas del split en config.py no están en orden creciente"]
    return []


def _contrato(raiz: Path) -> list[str]:
    csv = raiz / config.CSV_CRUDO
    if not csv.exists():
        return []  # ya reportado en _archivos
    return [f"Contrato de datos: {p}" for p in validar(pd.read_csv(csv))]


def verificar_entorno(raiz: Path = Path(".")) -> list[str]:
    """Devuelve la lista de problemas del entorno (vacía si todo está bien)."""
    raiz = Path(raiz)
    return _entorno() + _archivos(raiz) + _particiones() + _contrato(raiz)


def main() -> int:
    problemas = verificar_entorno()
    if problemas:
        print("SMOKE FALLÓ:")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print("SMOKE OK: entorno, datos y contrato en orden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
