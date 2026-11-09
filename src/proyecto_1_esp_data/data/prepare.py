"""Tabla diaria por estación, target, split temporal y línea base.

Flujo: filas por hora -> tabla diaria por estación -> target "¿el PM2.5 medio de
mañana supera el umbral?" -> split por fechas fijas (config.py) -> línea base
"mañana = hoy".

Decisiones que evitan fuga de datos (ver docs/dataset-card.md, sección 7):
- El relleno de huecos (forward fill) solo usa valores pasados y máximo 3 horas.
- "Mañana" se calcula por fecha de calendario, no por posición de fila: si un día
  se descarta, el target del día anterior queda vacío en vez de saltar al siguiente.
- Una fila pertenece a una partición solo si su día **y** el día del target caen
  dentro de ella; así ningún target de train mira datos de validación.
"""

from __future__ import annotations

import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

from proyecto_1_esp_data import config

COLUMNAS_DIARIAS = [*config.COLUMNAS_CONTAMINANTES, *config.COLUMNAS_METEO]
ESTACION_DEL_ANO = {
    12: "invierno",
    1: "invierno",
    2: "invierno",
    3: "primavera",
    4: "primavera",
    5: "primavera",
    6: "verano",
    7: "verano",
    8: "verano",
    9: "otono",
    10: "otono",
    11: "otono",
}


def cargar_crudo(ruta=config.CSV_CRUDO) -> pd.DataFrame:
    """Lee el CSV crudo unido por `download.py`."""
    return pd.read_csv(ruta)


def _moda(serie: pd.Series):
    """Valor más frecuente (dirección de viento dominante del día)."""
    modas = serie.mode()
    return modas.iloc[0] if len(modas) else None


def tabla_diaria(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega las filas por hora a una fila por (estación, día) con calendario completo.

    - Rellena huecos de hasta `RELLENO_MAX_HORAS` horas seguidas, por estación y
      solo hacia adelante (valores pasados).
    - Un día con menos de `HORAS_VALIDAS_MIN_POR_DIA` horas válidas de PM2.5 queda
      con `pm25` vacío (día no válido).
    - Cada estación tiene todos los días del calendario, válidos o no.
    """
    d = df.copy()
    d["fecha"] = pd.to_datetime(d[["year", "month", "day"]])
    d = d.sort_values(["station", "fecha", "hour"])
    d[COLUMNAS_DIARIAS] = d.groupby("station")[COLUMNAS_DIARIAS].ffill(
        limit=config.RELLENO_MAX_HORAS
    )

    grupos = d.groupby(["station", "fecha"])
    diaria = grupos[COLUMNAS_DIARIAS].mean()
    diaria["wd"] = grupos["wd"].agg(_moda)
    diaria["horas_pm25"] = grupos["PM2.5"].count()
    diaria = diaria.rename(columns={"PM2.5": "pm25"}).reset_index()

    # Día no válido: no se usa su PM2.5 (ni como feature ni como target)
    invalido = diaria["horas_pm25"] < config.HORAS_VALIDAS_MIN_POR_DIA
    diaria.loc[invalido, "pm25"] = float("nan")

    # Calendario completo por estación, para que "mañana" sea el día de calendario
    fechas = pd.date_range(diaria["fecha"].min(), diaria["fecha"].max(), freq="D")
    indice = pd.MultiIndex.from_product(
        [sorted(diaria["station"].unique()), fechas], names=["station", "fecha"]
    )
    diaria = diaria.set_index(["station", "fecha"]).reindex(indice).reset_index()
    return diaria


def agregar_target_y_features(diaria: pd.DataFrame) -> pd.DataFrame:
    """Agrega el target (mañana > umbral), rezagos de PM2.5 y estación del año.

    Devuelve solo las filas con target conocido (día de mañana válido).
    """
    t = diaria.sort_values(["station", "fecha"]).copy()
    por_estacion = t.groupby("station")["pm25"]
    t["pm25_manana"] = por_estacion.shift(-1)
    t["pm25_lag1"] = por_estacion.shift(1)
    t["pm25_lag2"] = por_estacion.shift(2)
    t["hoy_supera"] = (
        (t["pm25"] > config.UMBRAL_PM25).astype("float").where(t["pm25"].notna())
    )
    t["fecha_objetivo"] = t["fecha"] + pd.Timedelta(days=1)
    t["estacion_ano"] = t["fecha"].dt.month.map(ESTACION_DEL_ANO)

    t = t[t["pm25_manana"].notna()].copy()
    t["target"] = (t["pm25_manana"] > config.UMBRAL_PM25).astype(int)
    return t.drop(columns=["pm25_manana"]).reset_index(drop=True)


def construir_tabla_modelo(df: pd.DataFrame) -> pd.DataFrame:
    """Crudo por hora -> tabla diaria con target y features, lista para dividir."""
    return agregar_target_y_features(tabla_diaria(df))


def dividir(tabla: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split temporal por fechas fijas de `config.py`: train, val, produccion.

    Una fila entra a una partición si su día y el día del target caen dentro de
    ella. Nunca se mezclan ni se barajan filas.
    """
    ventanas = {
        "train": (config.TRAIN_INICIO, config.TRAIN_FIN),
        "val": (config.VAL_INICIO, config.VAL_FIN),
        "produccion": (config.PRODUCCION_INICIO, config.PRODUCCION_FIN),
    }
    partes = {}
    for nombre, (inicio, fin) in ventanas.items():
        en_ventana = (tabla["fecha"] >= inicio) & (tabla["fecha_objetivo"] <= fin)
        partes[nombre] = tabla[en_ventana].reset_index(drop=True)
    return partes


def baseline_persistencia(tabla: pd.DataFrame) -> pd.Series:
    """Línea base "mañana = hoy": predice para mañana la clase de hoy.

    Las filas con hoy no válido quedan con predicción vacía y se excluyen al evaluar.
    """
    return tabla["hoy_supera"]


def metricas(y_real: pd.Series, y_pred: pd.Series) -> dict[str, float | int]:
    """Sensibilidad (métrica principal), precisión y F1, sobre filas con predicción."""
    ok = y_pred.notna()
    y_r, y_p = y_real[ok].astype(int), y_pred[ok].astype(int)
    return {
        "n": int(ok.sum()),
        "sensibilidad": float(recall_score(y_r, y_p, zero_division=0)),
        "precision": float(precision_score(y_r, y_p, zero_division=0)),
        "f1": float(f1_score(y_r, y_p, zero_division=0)),
    }


def metricas_por_estacion(tabla: pd.DataFrame, y_pred: pd.Series) -> pd.DataFrame:
    """Mismas métricas, una fila por estación."""
    filas = {}
    for estacion, idx in tabla.groupby("station").groups.items():
        filas[estacion] = metricas(tabla.loc[idx, "target"], y_pred.loc[idx])
    return pd.DataFrame(filas).T
