"""Configuración central del proyecto: rutas, fechas del split, umbrales y semillas.

Todo lo que sea una decisión del proyecto vive aquí (no repartido por el código),
para que el split, el target y el contrato sean reproducibles y fáciles de auditar.
"""

from __future__ import annotations

from pathlib import Path

# --- Rutas (relativas a la raíz del repositorio; nunca absolutas) -----------------
DATA_RAW = Path("data/raw")
CSV_CRUDO = DATA_RAW / "calidad_aire_beijing.csv"
METADATA = DATA_RAW / "metadata.json"

# --- Reproducibilidad -------------------------------------------------------------
SEMILLA = 42

# --- Target ---------------------------------------------------------------------
# Problema: ¿el promedio diario de PM2.5 de MAÑANA superará el umbral?
# 75 µg/m³ = meta intermedia 1 de la OMS (guía 2021, promedio de 24 h) y también el
# nivel II del estándar chino GB 3095-2012. Verificar la cifra antes de citarla.
UMBRAL_PM25 = 75.0
HORAS_VALIDAS_MIN_POR_DIA = 18  # un día con menos de 18 horas válidas no se usa
RELLENO_MAX_HORAS = 3  # forward fill de huecos de máximo 3 horas seguidas

# --- Split temporal con fechas fijas (nunca aleatorio: hay estacionalidad y fuga) ---
TRAIN_INICIO = "2013-03-01"
TRAIN_FIN = "2014-12-31"
VAL_INICIO = "2015-01-01"
VAL_FIN = "2015-12-31"
PRODUCCION_INICIO = "2016-01-01"
PRODUCCION_FIN = "2017-02-28"

# Ventanas para comparar drift: dos ventanas de 12 meses completos, así la
# estacionalidad (invierno vs verano) no se confunde con drift real.
DRIFT_REFERENCIA = (VAL_INICIO, VAL_FIN)
DRIFT_ACTUAL = ("2016-01-01", "2016-12-31")

# --- Contrato de datos ------------------------------------------------------------
ESTACIONES_ESPERADAS = 12
FILAS_POR_ESTACION = 35_064  # 1.461 días x 24 h (2013-03-01 a 2017-02-28)
COLUMNAS_CONTAMINANTES = ["PM2.5", "PM10", "SO2", "NO2", "CO", "O3"]
COLUMNAS_METEO = ["TEMP", "PRES", "DEWP", "RAIN", "WSPM"]
DIRECCIONES_VIENTO = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]  # fmt: skip

# Rangos físicos plausibles (mín, máx). Se calcularon sobre los datos reales con
# margen; un valor fuera de rango indica error de captura, no un día extremo.
RANGOS = {
    "PM2.5": (0, 1000),
    "PM10": (0, 1000),
    "SO2": (0, 1000),
    "NO2": (0, 500),
    "CO": (0, 20_000),
    "O3": (0, 1200),
    "TEMP": (-40, 50),
    "PRES": (900, 1100),
    "DEWP": (-60, 40),
    "RAIN": (0, 200),
    "WSPM": (0, 50),
}
MAX_FRACCION_NULOS = 0.10  # por columna, sobre el dataset completo
# PM10 incluye a PM2.5, así que PM10 >= PM2.5. En los datos reales ~5 % de las
# filas lo incumplen por ruido del sensor: se tolera hasta este porcentaje.
MAX_FRACCION_PM10_MENOR_PM25 = 0.10

# --- Monitoreo de drift (Evidently) -----------------------------------------------
REPORTES = Path("reports")
DRIFT_COLUMNAS_NUM = [
    "pm25", "PM10", "SO2", "NO2", "CO", "O3",
    "TEMP", "PRES", "DEWP", "RAIN", "WSPM", "pm25_lag1", "pm25_lag2",
]  # fmt: skip
DRIFT_COLUMNAS_CAT = ["wd", "station", "estacion_ano", "target"]
# Una columna tiene drift si su distancia entre ventanas supera este valor
# (Wasserstein normalizada en numéricas, Jensen-Shannon en categóricas).
# 0.1 es el valor por defecto de Evidently; se conserva porque las ventanas de
# 12 meses ya neutralizan la estacionalidad.
DRIFT_UMBRAL_COLUMNA = 0.1
# Se declara drift del dataset si al menos esta proporción de columnas lo tiene.
# Medido en los datos: entre años consecutivos la proporción varía de 0,18 a 0,65,
# así que el drift es una ALERTA que se revisa, nunca un reentrenamiento automático
# (ver docs/politica-de-reentrenamiento.md).
DRIFT_UMBRAL_COMPARTIDO = 0.5
