"""Variables de entrada y pipeline de preprocesamiento."""

from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

TARGET = "target"
NUMERICAS = [
    "pm25",
    "PM10",
    "SO2",
    "NO2",
    "CO",
    "O3",
    "TEMP",
    "PRES",
    "DEWP",
    "RAIN",
    "WSPM",
    "pm25_lag1",
    "pm25_lag2",
]
CATEGORICAS = ["wd", "station", "estacion_ano"]
COLUMNAS_X = NUMERICAS + CATEGORICAS


def construir_preprocesador() -> ColumnTransformer:
    """Imputación + escalado para numéricas; imputación + one-hot para categóricas.
    """
    numerico = Pipeline(
        [
            ("imputar", SimpleImputer(strategy="median")),
            ("escalar", StandardScaler()),
        ]
    )
    categorico = Pipeline(
        [
            ("imputar", SimpleImputer(strategy="constant", fill_value="desconocido")),
            ("codificar", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        [("num", numerico, NUMERICAS), ("cat", categorico, CATEGORICAS)],
        remainder="drop",
    )