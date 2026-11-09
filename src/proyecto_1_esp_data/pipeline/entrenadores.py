"""Entrenadores disponibles para el pipeline.

Cada entrenador recibe las particiones de `prepare.dividir` y devuelve un `Candidato`:
un modelo ya ajustado, con la función que predice sobre una partición.

Para agregar un modelo (por ejemplo, LightGBM):
1. Escribir `def entrenar_lightgbm(partes) -> Candidato`. Ajustar **solo con**
   `partes["train"]` (imputadores y escaladores incluidos) y usar `config.SEMILLA`.
2. Registrarlo en `ENTRENADORES`.
3. Correr el pipeline con `--modelo lightgbm`.

El pipeline nunca promueve un candidato: solo lo evalúa y lo deja registrado.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from proyecto_1_esp_data import config
from proyecto_1_esp_data.data import prepare


@dataclass(frozen=True)
class Candidato:
    """Un modelo entrenado, listo para evaluarse."""

    nombre: str
    # Recibe una partición (tabla diaria) y devuelve 1.0 / 0.0 (o NaN si no puede predecir)
    predecir: Callable[[pd.DataFrame], pd.Series]
    parametros: dict = field(default_factory=dict)


def entrenar_baseline(partes: dict[str, pd.DataFrame]) -> Candidato:
    """Línea base "mañana = hoy": no aprende nada, así que `partes` no se usa."""
    return Candidato(
        nombre="baseline_persistencia",
        predecir=prepare.baseline_persistencia,
        parametros={"regla": "manana = hoy", "umbral_pm25": config.UMBRAL_PM25},
    )


ENTRENADORES: dict[str, Callable[[dict[str, pd.DataFrame]], Candidato]] = {
    "baseline": entrenar_baseline,
}
