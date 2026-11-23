"""Pipeline: preprocesamiento + clasificador"""

from __future__ import annotations

from lightgbm import LGBMClassifier
from sklearn.pipeline import Pipeline

from proyecto_1_esp_data import config
from proyecto_1_esp_data.features import construir_preprocesador


def construir_pipeline() -> Pipeline:
    """Pipeline sin ajustar: preprocesador + LightGBM."""
    return Pipeline(
        [
            ("preprocesador", construir_preprocesador()),
            (
                "clasificador",
                LGBMClassifier(
                    n_estimators=300,
                    learning_rate=0.05,
                    num_leaves=31,
                    class_weight="balanced",
                    random_state=config.SEMILLA,
                    verbose=-1,
                ),
            ),
        ]
    )
