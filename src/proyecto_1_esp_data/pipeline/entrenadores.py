"""Entrenadores disponibles para el pipeline.

Cada entrenador recibe las particiones de `prepare.dividir` y devuelve un `Candidato`:
un modelo ya ajustado, con la función que predice sobre una partición.

Modelos disponibles:
- `baseline`: "mañana = hoy", no aprende nada.
- `lightgbm`: el mismo pipeline que entrena `make train` (`model.py`), ajustado
  **solo con** `partes["train"]`, imputadores y escaladores incluidos.

Para agregar otro modelo: escribir `def entrenar_<nombre>(partes) -> Candidato`,
registrarlo en `ENTRENADORES` y correr el pipeline con `--modelo <nombre>`.

El pipeline nunca promueve un candidato: solo lo evalúa y lo deja registrado.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from proyecto_1_esp_data import config
from proyecto_1_esp_data.data import prepare
from proyecto_1_esp_data.features import COLUMNAS_X, TARGET
from proyecto_1_esp_data.model import construir_pipeline


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


def entrenar_lightgbm(partes: dict[str, pd.DataFrame]) -> Candidato:
    """El LightGBM de `model.py`, ajustado solo con la partición de train."""
    train = partes["train"]
    pipeline = construir_pipeline().fit(train[COLUMNAS_X], train[TARGET])

    def predecir(tabla: pd.DataFrame) -> pd.Series:
        proba = pipeline.predict_proba(tabla[COLUMNAS_X])[:, 1]
        return pd.Series(
            (proba >= config.UMBRAL_DECISION).astype(float), index=tabla.index
        )

    clasificador = pipeline.named_steps["clasificador"].get_params()
    parametros = {
        clave: clasificador[clave]
        for clave in (
            "n_estimators",
            "learning_rate",
            "num_leaves",
            "class_weight",
            "random_state",
        )
    }
    parametros["umbral_decision"] = config.UMBRAL_DECISION
    return Candidato(nombre="lightgbm", predecir=predecir, parametros=parametros)


ENTRENADORES: dict[str, Callable[[dict[str, pd.DataFrame]], Candidato]] = {
    "baseline": entrenar_baseline,
    "lightgbm": entrenar_lightgbm,
}
