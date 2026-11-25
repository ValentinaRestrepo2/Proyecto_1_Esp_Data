# Predicción de días con mala calidad del aire en Beijing

Proyecto 1 (Universidad de Medellín). El objetivo es crear un predictor de días con mala calidad del aire en Beijing: para cada estación de monitoreo, predice si **mañana el promedio de PM2.5 superará 75 µg/m³**, con datos horarios reales de 12 estaciones (2013-2017).

El foco del proyecto es el **ciclo de vida** (datos validados, split sin fuga, reproducibilidad), no la calidad del modelo.

## El problema

- **Tarea:** clasificación binaria por estación y día.
- **Target:** `PM2.5 medio de mañana > 75 µg/m³` (`UMBRAL_PM25` en `config.py`).
- **Por qué 75 µg/m³:** es el límite diario (24 h) de PM2.5 del [estándar chino GB 3095-2012](https://english.mee.gov.cn/Resources/standards/Air_Environment/quality_standard1/201605/t20160511_337502.shtml), nivel II, y la meta intermedia 1 de la [guía de calidad del aire de la OMS de 2021](https://www.ncbi.nlm.nih.gov/books/NBK574591/table/ch3.tab24/).
- **Métrica principal:** sensibilidad (no avisar un día malo es el error más costoso), con precisión mínima, F1 y PR-AUC de apoyo.
- **Línea base:** "mañana = hoy". Sensibilidad de **0,64** en validación y **0,59** en producción simulada. Es el número a superar.
- **Datos:** [Beijing Multi-Site Air Quality](https://archive.ics.uci.edu/dataset/501) (UCI), licencia CC BY 4.0. Detalles en [`docs/dataset-card.md`](docs/dataset-card.md).

## Objetivo de análisis (CRISP-DM, fase 1)

| Campo | Contenido |
|---|---|
| **Problema de negocio** | En Beijing hay días en que la contaminación por PM2.5 es dañina para la salud, y la población se entera cuando ya está expuesta. No hay un aviso anticipado por estación que permita prepararse el día anterior. |
| **Pregunta de negocio** | *"Con lo que mide hoy cada estación, ¿puedo saber si mañana el aire será malo, para avisar a tiempo y que la gente reduzca su exposición?"* |
| **Objetivo de análisis** | Construir un modelo que prediga, para cada estación, si mañana el PM2.5 promedio superará 75 µg/m³, porque a partir de ese nivel la contaminación es perjudicial para la salud según el límite diario del estándar chino GB 3095-2012 (nivel II) y la meta intermedia 1 de la guía de calidad del aire de la OMS (2021). |
| **Criterio de éxito analítico** | Superar la sensibilidad de la línea base "mañana = hoy", tanto en validación (2015) como en producción simulada (2016-01 a 2017-02). |
| **Criterio de éxito de negocio** | Es exitoso si predice los días malos sin generar falsas alarmas. |
| **Riesgos** | 1) **El modelo no supera la línea base:** no predice mejor que suponer que mañana será igual que hoy.<br>2) **Sobreajuste:** el modelo memoriza los patrones de los años de entrenamiento y no predice bien días nuevos.<br>3) **Fuga de datos:** el modelo usa información del futuro al entrenar y sus métricas parecen mejores de lo que son.<br>4) **Pérdida de rendimiento con el tiempo:** la contaminación y el clima cambian, y el modelo deja de superar la línea base en los datos recientes.<br>5) **Rendimiento desigual por estación:** el modelo funciona bien en promedio, pero en algunas estaciones predice peor que la línea base.<br>6) **Datos erróneos o insuficientes:** fallas del sensor (valores tope, huecos largos) impiden construir una tabla confiable para entrenar.<br>7) **La fuente cambia o desaparece:** UCI actualiza o retira el archivo y no hay datos para entrenar.<br>8) **Versiones de librerías incompatibles:** una actualización rompe el proyecto y no se puede ejecutar. |

**Planes de mitigación**

1. **El modelo no supera la línea base:** se compara siempre contra "mañana = hoy" con la misma métrica (sensibilidad) y en las mismas particiones.
2. **Sobreajuste:** el modelo se evalúa en dos periodos que nunca vio al entrenar (validación 2015 y producción simulada 2016-2017).
3. **Fuga de datos:** split temporal con fechas fijas, preprocesamiento ajustado solo con train y pruebas que verifican que el modelo no usa datos de mañana.
4. **Pérdida de rendimiento con el tiempo:** el modelo se evalúa también en producción simulada (2016-2017), un periodo posterior a la validación, para medir cuánto cae el rendimiento con el tiempo.
5. **Rendimiento desigual por estación:** métricas reportadas por estación, no solo el promedio.
6. **Datos erróneos o insuficientes:** contrato de datos con rangos y tolerancias que detiene el proceso si no se cumple; un día solo se usa si tiene 18 horas válidas o más.
7. **La fuente cambia o desaparece:** hash SHA-256 del archivo original, que hace fallar la descarga si el archivo cambia.
8. **Versiones de librerías incompatibles:** versiones fijas en `uv.lock`, Python 3.12 y `pandas<3`; el CI corre las pruebas en cada cambio y verifica que `uv.lock` coincida con `pyproject.toml`.

## Resultados

Modelo: LightGBM (300 árboles, `class_weight="balanced"`, semilla 42) con las 16 variables de `features.py` y umbral de decisión 0,5. Se entrena solo con train (2013-03 a 2014-12); la imputación y el escalado se ajustan dentro del pipeline, sin ver validación ni producción. Se reproduce con `make train`.

| Partición | Modelo | Sensibilidad | Precisión | F1 | Filas |
|---|---|---|---|---|---|
| Validación (2015) | Línea base | 0,641 | 0,643 | 0,642 | 4.301 |
| Validación (2015) | **LightGBM** | **0,739** | **0,684** | **0,711** | 4.326 |
| Producción simulada (2016-01 a 2017-02) | Línea base | 0,591 | 0,588 | 0,589 | 4.990 |
| Producción simulada (2016-01 a 2017-02) | **LightGBM** | **0,647** | **0,611** | **0,628** | 5.031 |

El modelo supera a la línea base en las tres métricas y en las dos particiones: en validación detecta 74 de cada 100 días malos, frente a 64.

### Sensibilidad por estación (validación 2015)

Se calculan con `prepare.metricas_por_estacion` sobre la partición de validación, con el modelo que entrena `make train`; la línea base es "mañana = hoy". Cada estación tiene unos 360 días evaluados.

| Estación | Línea base | LightGBM | Diferencia (puntos) |
|---|---|---|---|
| Wanliu | 0,671 | **0,836** | +16,5 |
| Guanyuan | 0,660 | **0,796** | +13,6 |
| Aotizhongxin | 0,662 | **0,797** | +13,5 |
| Nongzhanguan | 0,644 | **0,773** | +12,9 |
| Shunyi | 0,636 | **0,755** | +11,9 |
| Dingling | 0,573 | **0,691** | +11,8 |
| Wanshouxigong | 0,645 | **0,761** | +11,6 |
| Dongsi | 0,660 | **0,765** | +10,5 |
| Gucheng | 0,622 | **0,725** | +10,3 |
| Tiantan | 0,653 | **0,755** | +10,2 |
| Changping | 0,595 | 0,598 | +0,3 |
| Huairou | **0,651** | 0,562 | −8,9 |

### Limitaciones

- **No mejora en todas las estaciones.** En **Huairou** el modelo detecta 56 de cada 100 días malos, frente a 65 de la línea base (−8,9 puntos), aunque su precisión es mayor (0,709). En **Changping** empata con la línea base (0,598 frente a 0,595). Las dos son estaciones de las afueras, al norte de la ciudad; la causa no se ha investigado. El promedio general (0,739) oculta estas diferencias, por eso se reportan por estación.
- **Las métricas por estación tienen bastante incertidumbre.** Con unos 360 días por estación (de ellos, alrededor de 130 a 150 días malos), cada sensibilidad tiene un margen de error aproximado de ±8 puntos. Las mejoras de más de 10 puntos superan ese margen; la caída de Huairou está cerca de él, así que conviene confirmarla con más datos.
- **Pierde rendimiento con el tiempo.** La sensibilidad baja de 0,74 en validación a 0,65 en producción. Coincide con un cambio en los datos: los días malos bajan de 39,2 % a 36,6 %. No hay monitoreo automático de ese cambio ni política de reentrenamiento: si se usara en serio, habría que medirlo y decidir cuándo reentrenar.
- **La comparación no usa exactamente las mismas filas.** La línea base no puede predecir cuando falta el PM2.5 de hoy; el modelo sí, porque imputa. Son menos del 1 % de las filas.
- **La mejora es moderada.** Buena parte de la señal ya está en el PM2.5 de hoy.
- **Solo usa datos de hoy.** No incluye pronóstico meteorológico de mañana, así que le cuesta anticipar cambios bruscos por viento o lluvia.
- **Las 12 estaciones no son independientes** (correlación diaria mínima de 0,88): cuando el modelo falla un día, suele fallar en varias estaciones a la vez.
- **El umbral de decisión de 0,5 no se ha ajustado.**
- **Unidades asumidas.** La fuente no declara las unidades; se asumen µg/m³ (ver la dataset card).

## Cómo ejecutarlo

Requisitos: [Git](https://git-scm.com/) y [uv](https://docs.astral.sh/uv/). `uv` instala Python 3.12 por su cuenta.

```
git clone https://github.com/ValentinaRestrepo2/Proyecto_1_Esp_Data.git
cd Proyecto_1_Esp_Data
make setup      # instala dependencias desde uv.lock
make data       # descarga y une los datos (unos 34 MB, no se versionan)
make train      # entrena el modelo y muestra métricas (descarga los datos si faltan)
make test       # pruebas
make app        # abre la app de Streamlit (entrena si no hay modelo)
make api        # levanta la API; documentación en http://127.0.0.1:8000/docs
```

**En Windows no hay `make` por defecto.** Cada comando tiene su equivalente directo:

| `make` | Equivalente |
|---|---|
| `make setup` | `uv sync` |
| `make data` | `uv run python -m proyecto_1_esp_data.data.download` |
| `make train` | `uv run python -m proyecto_1_esp_data.train` |
| `make test` | `uv run pytest` |
| `make app` | `uv run streamlit run app/streamlit_app.py` |
| `make api` | `uv run uvicorn app.api_fastapi:app --reload` |
| `make lint` | `uv run ruff check .` |

La descarga es reproducible: `data/raw/metadata.json` guarda el hash SHA-256 del ZIP original. Si UCI cambiara el archivo, la descarga falla en vez de usar datos distintos sin avisar.

## Reproducibilidad

- Dependencias fijas en `uv.lock`; Python 3.12 en `.python-version`.
- Semilla en `config.py` (`SEMILLA`), pasada de forma explícita.
- Split temporal con **fechas fijas** en `config.py`, sin `datetime.now()` ni mezcla aleatoria:

| Partición | Periodo |
|---|---|
| Train | 2013-03-01 a 2014-12-31 |
| Validación | 2015-01-01 a 2015-12-31 |
| Producción (simulada) | 2016-01-01 a 2017-02-28 |

## Estructura

```
src/proyecto_1_esp_data/
  config.py            fechas del split, umbrales, semilla, reglas del contrato
  data/download.py     descarga reproducible con hash
  data/contract.py     contrato de datos (rangos, relaciones, volumen)
  data/prepare.py      tabla diaria, target, split temporal y línea base
  features.py          variables de entrada y preprocesador
  model.py             preprocesador + LightGBM
  train.py             entrenamiento, evaluación y guardado del modelo
  predict.py           inferencia para una fila
app/                   API (FastAPI) y app (Streamlit)
tests/                 pruebas (datos, features, predicción, API, notebooks)
notebooks/01_eda.ipynb análisis exploratorio (sin salidas)
docs/dataset-card.md   ficha del dataset
```

## Calidad del código

```
make check                       # ruff + pruebas
```

Los notebooks se guardan **sin salidas** (una prueba falla si no). El CI de GitHub corre formato, lint y pruebas en cada push y pull request.

## Documentación

- [`docs/dataset-card.md`](docs/dataset-card.md): procedencia, licencia, nulos, límites y riesgos de fuga de datos.

## Estado y pendientes

Lo que no está hecho, dicho con su motivo:

| Pendiente | Motivo |
|---|---|
| Orquestación y monitoreo de drift | Se retiraron para mantener el proyecto simple. Hoy no hay alerta automática si los datos cambian ni un pipeline programado |
| `make train` reemplaza el modelo sin revisión | Sobrescribe `models/clasificador_pm25.joblib` y no conserva el anterior; no hay registro de versiones del modelo |
| Ficha del modelo | No está escrita; los resultados y las limitaciones están en este README |
| Dockerfile | La API funciona (`make api`), pero no hay contenedor |
| Unidades de los contaminantes | La ficha de UCI no las declara; en la dataset card se asumen µg/m³ por la escala observada y está marcado |
