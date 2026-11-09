# Dataset card: Beijing Multi-Site Air Quality

## 1. Procedencia

| Campo | Valor |
|---|---|
| Nombre | Beijing Multi-Site Air Quality Data |
| Fuente | UCI Machine Learning Repository, dataset 501: <https://archive.ics.uci.edu/dataset/501> |
| Autor | Song Chen (donado a UCI el 19/09/2019) |
| DOI | <https://doi.org/10.24432/C5RK5G> |
| Artículo de referencia | Zhang et al. (2017), "Cautionary tales on air-quality improvement in Beijing", *Proceedings of the Royal Society A* |
| Licencia | **CC BY 4.0**: <https://creativecommons.org/licenses/by/4.0/legalcode>. Se puede usar y redistribuir citando la fuente. |
| Cobertura | 1 de marzo de 2013 a 28 de febrero de 2017, datos horarios |
| Tamaño | 420.768 filas = 12 estaciones x 35.064 horas; 18 columnas |

Los datos provienen de 12 estaciones nacionales de monitoreo de calidad del aire de Beijing. Las variables meteorológicas se asignaron desde la estación de la Administración Meteorológica de China más cercana a cada estación (según la ficha de UCI).

**Cómo se obtiene (reproducible):**

```
uv run python -m proyecto_1_esp_data.data.download
```

El script baja el ZIP oficial, une los 12 CSV de estaciones con pandas y valida el volumen. Guarda `data/raw/metadata.json` con fuente, licencia, filas, columnas y el **hash SHA-256 del ZIP**. Si UCI cambiara el archivo, la descarga falla en vez de usar datos distintos sin avisar. El CSV unido (unos 34 MB) **no se versiona**; `metadata.json` sí.

## 2. Diccionario de datos

| Columna | Tipo | Descripción | Nulos |
|---|---|---|---|
| `No` | int | Número de fila dentro de cada estación (1 a 35.064) | 0 % |
| `year`, `month`, `day`, `hour` | int | Marca de tiempo horaria (hora 0 a 23) | 0 % |
| `PM2.5` | float | Partículas finas, µg/m³ | 2,08 % |
| `PM10` | float | Partículas gruesas, µg/m³ | 1,53 % |
| `SO2` | float | Dióxido de azufre | 2,14 % |
| `NO2` | float | Dióxido de nitrógeno | 2,88 % |
| `CO` | float | Monóxido de carbono | 4,92 % |
| `O3` | float | Ozono | 3,16 % |
| `TEMP` | float | Temperatura, °C | 0,09 % |
| `PRES` | float | Presión, hPa | 0,09 % |
| `DEWP` | float | Temperatura del punto de rocío, °C | 0,10 % |
| `RAIN` | float | Precipitación, mm | 0,09 % |
| `wd` | texto | Dirección del viento (16 puntos del compás) | 0,43 % |
| `WSPM` | float | Velocidad del viento, m/s | 0,08 % |
| `station` | texto | Una de 12 estaciones | 0 % |

Nota sobre unidades: la ficha de UCI no declara unidades por columna. Las de PM2.5 y PM10 (µg/m³) son las habituales; para los demás contaminantes se asumen µg/m³ por la escala observada (por ejemplo CO entre 100 y 10.000). Confirmarlo en el artículo de referencia antes de citar valores absolutos.

## 3. Valores nulos

UCI marca los faltantes como `NA`. En total el nivel de nulos es bajo (máximo 4,92 % por columna), pero **no es uniforme**:

- **CO** es la más incompleta (4,92 %); en la estación Dongsi llega a 9,1 %.
- **PM2.5**, la variable del target, tiene entre 1,1 % (Wanliu) y 2,7 % (Huairou) de nulos por estación.
- **Los huecos vienen en rachas.** La racha más larga de PM2.5 consecutivos faltantes es de **343 horas** (unos 14 días). Por eso no se rellena sin límite.
- Los nulos de `wd` se concentran en las estaciones Shunyi (483 filas), Huairou (302) y Gucheng (159).
- Las columnas meteorológicas casi no tienen nulos (menos de 0,11 %).

### Estrategia

1. **Día válido:** el target se calcula con el promedio diario de PM2.5 por estación. Un día con **menos de 18 horas válidas** no se usa (`HORAS_VALIDAS_MIN_POR_DIA` en `config.py`). Quedan 17.294 de 17.532 días estación (98,6 %).
2. **Relleno acotado:** se rellena hacia adelante (*forward fill*) solo huecos de **máximo 3 horas seguidas** (`RELLENO_MAX_HORAS`). Los huecos más largos quedan como nulos y el día se descarta si no llega a 18 horas.
3. **Imputación de variables predictoras:** cualquier imputador o escalador se ajusta **solo con train** y se aplica a validación y producción.
4. **No se eliminan filas con nulos** en el dataset crudo; la decisión se toma después, sobre la tabla diaria.

## 4. Valores extremos y calidad

- Hay valores altos de PM2.5 reales en episodios de contaminación severa (933 horas con más de 500 µg/m³). **No se tratan como errores.**
- PM2.5 y PM10 tienen valores de exactamente 999 (1 y 3 filas): posible tope del sensor. Se dejan y se documentan.
- PM10 es menor que PM2.5 en cerca del 5 % de las filas, lo cual es físicamente inconsistente (PM10 incluye a PM2.5). Es ruido de sensor; el contrato tolera hasta 10 %.
- El contrato de datos (`src/proyecto_1_esp_data/data/contract.py`) verifica: columnas, calendario, duplicados, rangos físicos, `DEWP <= TEMP`, PM10 vs PM2.5, direcciones del viento válidas, nulos por columna y volumen (12 x 35.064). Con los datos reales cumple todas las reglas.

## 5. Uso previsto y definición del problema

- **Tarea:** clasificación binaria. Dado el día de hoy en una estación, predecir si el **promedio de PM2.5 de mañana superará 75 µg/m³** (`UMBRAL_PM25` en `config.py`).
- **Línea base:** "mañana = hoy" (el día siguiente repite la clase de hoy).
- **Métrica principal:** sensibilidad (detectar los días malos), con precisión mínima, F1 y PR-AUC como apoyo.
- **Split temporal con fechas fijas** (`config.py`), nunca aleatorio:

| Partición | Periodo | Días estación | % de días sobre el umbral |
|---|---|---|---|
| Train | 2013-03-01 a 2014-12-31 | 7.914 | 43,6 % |
| Validación | 2015-01-01 a 2015-12-31 | 4.337 | 39,1 % |
| Producción (simulada) | 2016-01-01 a 2017-02-28 | 5.043 | 36,7 % |

- **Variables derivadas:** estación, dirección del viento, estación del año (derivada del mes; se declara aquí por ser una variable construida), promedios diarios y rezagos de contaminantes y meteorología.
- **Evaluación por subgrupos:** se reportan métricas por estación, no solo el total.

## 6. Limitaciones

- **Una sola ciudad y cuatro años.** Un modelo entrenado aquí no se generaliza a otras ciudades ni a épocas con otras políticas ambientales.
- **Desbalance que cambia en el tiempo.** El porcentaje de días sobre el umbral baja de 43,6 % (train) a 36,7 % (producción). Es un cambio real de la distribución del target y se vigilará en el monitoreo.
- **Estaciones muy correlacionadas.** Las 12 estaciones están en la misma ciudad y el mismo día suele ser malo en casi todas. No son 12 muestras independientes; las métricas globales son optimistas frente a un caso con ciudades nuevas.
- **Las estaciones difieren.** El porcentaje de días sobre el umbral va de 31,7 % (Dingling) a 43,5 % (Dongsi). Por eso se evalúa por estación.
- **Estacionalidad fuerte.** Hay más contaminación en invierno (calefacción). Comparar ventanas de 12 meses completos evita confundir estación con drift.
- **Meteorología aproximada.** Proviene de la estación meteorológica más cercana, no del sitio exacto de medición.
- **Sin datos sensibles:** son mediciones ambientales, sin información personal. El dataset no declara valores sintéticos.

## 7. Riesgos de fuga de datos (*leakage*)

1. **Fuga temporal.** Un split aleatorio pone días del futuro en train y días del pasado en test, y el modelo "ve" el clima del periodo que debe predecir. Se evita con el split por fechas fijas y sin mezclar filas (`shuffle=False`). También hay que evitar variables construidas con información de mañana (ventanas centradas, rellenos hacia atrás).
2. **Fuga por preprocesamiento.** Calcular medias, escalas o imputaciones con todo el dataset filtra información de validación y producción. Todo imputador y escalador se ajusta con train únicamente. El *forward fill* se aplica por estación y no cruza las fronteras entre particiones.
3. **Fuga por el mismo día en otra estación.** Si un mismo día aparece en varias estaciones y se reparte entre particiones, el modelo ve el clima de ese día en train. Por eso el corte es por **fecha** para todas las estaciones a la vez, no por estación ni por fila.

## 8. Mantenimiento

- Si UCI cambia el archivo, el hash de `metadata.json` no coincide y la descarga falla. Hay que revisar el cambio antes de actualizarlo.
- Cualquier cambio de umbral, fechas o reglas del contrato se hace en `config.py` y queda en el historial de Git.
