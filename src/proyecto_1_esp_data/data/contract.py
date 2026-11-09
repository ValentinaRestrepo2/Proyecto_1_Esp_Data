"""Contratos de datos: reglas que los datos deben cumplir antes de usarse.

Hay dos contratos, uno por frontera del pipeline, porque protegen cosas distintas:

- **Crudo** (`validar`): ¿el dato que llegó de la fuente es físicamente creíble?
  Rangos, relaciones entre columnas (DEWP <= TEMP), nulos y volumen. Un fallo aquí
  significa que el sensor o la fuente cambiaron.
- **Procesado** (`validar_procesado`): ¿nuestro código construyó bien la tabla
  diaria? Calendario, target coherente con el PM2.5 de mañana y rezagos que vienen
  del pasado. Un fallo aquí significa un error nuestro, típicamente una fuga de datos.

`validar*` devuelve la lista de problemas (vacía si todo está bien).
`validar*_o_fallar` lanza `ContratoError` si hay alguno; así un dato roto detiene
el pipeline en vez de contaminar el entrenamiento.
"""

from __future__ import annotations

import pandas as pd

from proyecto_1_esp_data import config
from proyecto_1_esp_data.data import prepare

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


COLUMNAS_PROCESADO = [
    "station",
    "fecha",
    "fecha_objetivo",
    "target",
    "hoy_supera",
    "horas_pm25",
    "estacion_ano",
    "wd",
    *config.DRIFT_COLUMNAS_NUM,
]


def _vecino(tabla: pd.DataFrame, columna: str, dias: int, nombre: str) -> pd.DataFrame:
    """Valor de `columna` del día `fecha + dias` de la misma estación, como `nombre`."""
    otro = tabla[["station", "fecha", columna]].copy()
    otro["fecha"] = otro["fecha"] - pd.Timedelta(days=dias)
    otro = otro.rename(columns={columna: nombre})
    # Si hay filas duplicadas el merge multiplicaría filas; el duplicado ya se reporta aparte
    otro = otro.drop_duplicates(["station", "fecha"])
    return tabla[["station", "fecha"]].merge(otro, on=["station", "fecha"], how="left")


def validar_procesado(tabla: pd.DataFrame) -> list[str]:
    """Revisa la tabla diaria (salida de `prepare.construir_tabla_modelo`)."""
    faltan = [c for c in COLUMNAS_PROCESADO if c not in tabla.columns]
    if faltan:
        return [f"Faltan columnas: {faltan}"]
    if tabla.empty:
        return ["La tabla procesada está vacía"]

    problemas: list[str] = []

    if tabla["target"].isna().any() or not tabla["target"].isin([0, 1]).all():
        problemas.append("target debe ser 0 o 1, sin nulos")

    duplicadas = int(tabla.duplicated(["station", "fecha"]).sum())
    if duplicadas:
        problemas.append(f"{duplicadas} filas duplicadas por (estación, fecha)")

    # Relación entre columnas: el target mira exactamente un día hacia adelante
    salto = (tabla["fecha_objetivo"] - tabla["fecha"]) != pd.Timedelta(days=1)
    if salto.any():
        problemas.append(
            f"fecha_objetivo no es fecha + 1 día en {int(salto.sum())} filas"
        )

    # Relación entre filas: el target coincide con la regla aplicada al PM2.5 de mañana.
    # Solo se puede comprobar si el día siguiente también está en la tabla.
    manana = _vecino(tabla, "pm25", 1, "pm25_manana")
    esperado = (manana["pm25_manana"] > config.UMBRAL_PM25).astype(int)
    comprobable = manana["pm25_manana"].notna().to_numpy()
    incoherente = int(
        (esperado.to_numpy() != tabla["target"].to_numpy())[comprobable].sum()
    )
    if incoherente:
        problemas.append(
            f"target no coincide con PM2.5 de mañana > umbral en {incoherente} filas"
        )

    # Anti-fuga: los rezagos deben ser el PM2.5 de días PASADOS, no de hoy ni de mañana
    for columna, dias in (("pm25_lag1", 1), ("pm25_lag2", 2)):
        pasado = _vecino(tabla, "pm25", -dias, "pm25_pasado")["pm25_pasado"].to_numpy()
        ambos = tabla[columna].notna().to_numpy() & ~pd.isna(pasado)
        distintos = int((abs(tabla[columna].to_numpy() - pasado) > 1e-9)[ambos].sum())
        if distintos:
            problemas.append(
                f"{columna} no es el PM2.5 de {dias} día(s) atrás en {distintos} filas"
            )

    # Coherencia de las columnas derivadas
    horas = tabla["horas_pm25"]
    if not horas.between(0, 24).all():
        problemas.append("horas_pm25 debe estar entre 0 y 24")
    validas = tabla["pm25"].notna()
    pocas = int((horas[validas] < config.HORAS_VALIDAS_MIN_POR_DIA).sum())
    if pocas:
        problemas.append(
            f"{pocas} días con PM2.5 usan menos de {config.HORAS_VALIDAS_MIN_POR_DIA} horas"
        )

    lo, hi = config.RANGOS["PM2.5"]
    pm = tabla["pm25"].dropna()
    if not pm.between(lo, hi).all():
        problemas.append(f"pm25 fuera de [{lo}, {hi}]")

    mes_a_estacion = tabla["fecha"].dt.month.map(prepare.ESTACION_DEL_ANO)
    if (mes_a_estacion != tabla["estacion_ano"]).any():
        problemas.append("estacion_ano no coincide con el mes de la fecha")

    return problemas


def validar_procesado_o_fallar(tabla: pd.DataFrame) -> None:
    """Lanza `ContratoError` con todos los problemas si la tabla procesada no es válida."""
    problemas = validar_procesado(tabla)
    if problemas:
        raise ContratoError("; ".join(problemas))
