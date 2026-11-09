"""Contrato de datos: reglas que el dataset crudo debe cumplir antes de usarse.

`validar` devuelve la lista de problemas (vacía si todo está bien).
`validar_o_fallar` lanza `ContratoError` si hay alguno; así un dato roto
detiene el pipeline en vez de contaminar el entrenamiento.
"""

from __future__ import annotations

import pandas as pd

from proyecto_1_esp_data import config

COLUMNAS_TIEMPO = ["year", "month", "day", "hour"]
COLUMNAS_OBLIGATORIAS = [
    "No",
    *COLUMNAS_TIEMPO,
    *config.COLUMNAS_CONTAMINANTES,
    *config.COLUMNAS_METEO,
    "wd",
    "station",
]
LLAVE = ["station", *COLUMNAS_TIEMPO]


class ContratoError(ValueError):
    """El dataset no cumple el contrato de datos."""


def validar(df: pd.DataFrame, volumen: bool = True) -> list[str]:
    """Revisa el contrato y devuelve los problemas encontrados.

    `volumen=False` omite la regla de 12 estaciones x 35.064 filas (útil en
    pruebas con muestras pequeñas).
    """
    faltan = [c for c in COLUMNAS_OBLIGATORIAS if c not in df.columns]
    if faltan:
        # Sin las columnas no tiene sentido seguir con el resto de reglas.
        return [f"Faltan columnas: {faltan}"]

    problemas: list[str] = []

    if volumen:
        n_est = df["station"].nunique()
        if n_est != config.ESTACIONES_ESPERADAS:
            problemas.append(
                f"Estaciones: {n_est}, se esperaban {config.ESTACIONES_ESPERADAS}"
            )
        por_est = df.groupby("station").size()
        malas = por_est[por_est != config.FILAS_POR_ESTACION]
        if not malas.empty:
            problemas.append(
                f"Estaciones con filas distintas de {config.FILAS_POR_ESTACION}: "
                f"{malas.to_dict()}"
            )

    # Calendario válido
    for col, (lo, hi) in {
        "year": (2013, 2017),
        "month": (1, 12),
        "day": (1, 31),
        "hour": (0, 23),
    }.items():
        fuera = int((~df[col].between(lo, hi)).sum())
        if fuera:
            problemas.append(f"{col}: {fuera} valores fuera de [{lo}, {hi}]")

    duplicadas = int(df.duplicated(LLAVE).sum())
    if duplicadas:
        problemas.append(
            f"{duplicadas} filas duplicadas por (estación, año, mes, día, hora)"
        )

    # Rangos físicos (los nulos no cuentan: between() da False con NaN, se excluyen)
    for col, (lo, hi) in config.RANGOS.items():
        serie = df[col].dropna()
        fuera = int((~serie.between(lo, hi)).sum())
        if fuera:
            problemas.append(f"{col}: {fuera} valores fuera de [{lo}, {hi}]")

    # Coherencia física: el punto de rocío nunca supera la temperatura.
    # Igualdad sí es posible (aire saturado); superarla, no.
    sobre = int((df["DEWP"] > df["TEMP"]).sum())
    if sobre:
        problemas.append(f"DEWP > TEMP en {sobre} filas (imposible físicamente)")

    # PM10 incluye PM2.5; se tolera una fracción pequeña por ruido del sensor.
    ambos = df[["PM2.5", "PM10"]].dropna()
    if len(ambos):
        fraccion = float((ambos["PM10"] < ambos["PM2.5"]).mean())
        if fraccion > config.MAX_FRACCION_PM10_MENOR_PM25:
            problemas.append(
                f"PM10 < PM2.5 en {fraccion:.1%} de las filas "
                f"(tolerancia {config.MAX_FRACCION_PM10_MENOR_PM25:.0%})"
            )

    # Dirección del viento: solo las 16 del compás (o nulo)
    invalidas = df["wd"].dropna()
    invalidas = invalidas[~invalidas.isin(config.DIRECCIONES_VIENTO)]
    if len(invalidas):
        problemas.append(f"wd: valores no válidos {sorted(invalidas.unique())[:5]}")

    # Nulos por columna
    nulos = (
        df[config.COLUMNAS_CONTAMINANTES + config.COLUMNAS_METEO + ["wd"]].isna().mean()
    )
    exceso = nulos[nulos > config.MAX_FRACCION_NULOS]
    for col, frac in exceso.items():
        problemas.append(
            f"{col}: {frac:.1%} de nulos (máximo {config.MAX_FRACCION_NULOS:.0%})"
        )

    return problemas


def validar_o_fallar(df: pd.DataFrame, volumen: bool = True) -> None:
    """Lanza `ContratoError` con todos los problemas si el contrato no se cumple."""
    problemas = validar(df, volumen=volumen)
    if problemas:
        raise ContratoError("; ".join(problemas))
