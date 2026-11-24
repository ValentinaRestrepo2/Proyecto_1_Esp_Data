# Predicción de días con mala calidad del aire en Beijing

Proyecto final de MLOps (Universidad de Medellín). Predice, para cada estación de monitoreo, si **mañana el promedio de PM2.5 superará 75 µg/m³**, con datos horarios reales de 12 estaciones de Beijing (2013-2017).

El foco del proyecto es el **ciclo de vida** (datos validados, split sin fuga, monitoreo de drift, trazabilidad), no la calidad del modelo.

## El problema

- **Tarea:** clasificación binaria por estación y día.
- **Target:** `PM2.5 medio de mañana > 75 µg/m³` (`UMBRAL_PM25` en `config.py`).
- **Por qué 75 µg/m³:** es el límite diario (24 h) de PM2.5 del [estándar chino GB 3095-2012](https://english.mee.gov.cn/Resources/standards/Air_Environment/quality_standard1/201605/t20160511_337502.shtml), nivel II, y la meta intermedia 1 de la [guía de calidad del aire de la OMS de 2021](https://www.ncbi.nlm.nih.gov/books/NBK574591/table/ch3.tab24/).
- **Métrica principal:** sensibilidad (no avisar un día malo es el error más costoso), con precisión mínima, F1 y PR-AUC de apoyo.
- **Línea base:** "mañana = hoy". Sensibilidad de **0,64** en validación y **0,59** en producción simulada. Es el número a superar.
- **Datos:** [Beijing Multi-Site Air Quality](https://archive.ics.uci.edu/dataset/501) (UCI), licencia CC BY 4.0. Detalles en [`docs/dataset-card.md`](docs/dataset-card.md).

## Resultados

Modelo: LightGBM (300 árboles, `class_weight="balanced"`, semilla 42) con las 16 variables de `features.py` y umbral de decisión 0,5. Se entrena solo con train (2013-03 a 2014-12); la imputación y el escalado se ajustan dentro del pipeline, sin ver validación ni producción. Se reproduce con `make train`.

| Partición | Modelo | Sensibilidad | Precisión | F1 | Filas |
|---|---|---|---|---|---|
| Validación (2015) | Línea base | 0,641 | 0,643 | 0,642 | 4.301 |
| Validación (2015) | **LightGBM** | **0,739** | **0,684** | **0,711** | 4.326 |
| Producción simulada (2016-01 a 2017-02) | Línea base | 0,591 | 0,588 | 0,589 | 4.990 |
| Producción simulada (2016-01 a 2017-02) | **LightGBM** | **0,647** | **0,611** | **0,628** | 5.031 |

El modelo supera a la línea base en las tres métricas y en las dos particiones: en validación detecta 74 de cada 100 días malos, frente a 64. El pipeline (`--modelo lightgbm`) obtiene exactamente las mismas métricas que `make train`.

### Sensibilidad por estación (validación 2015)

Salen de `reports/candidato.json` (pipeline con `--modelo lightgbm`); los de la línea base, de su corrida anterior. Cada estación tiene unos 360 días evaluados.

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
- **Pierde rendimiento con el tiempo.** La sensibilidad baja de 0,74 en validación a 0,65 en producción. Coincide con el cambio en los datos: los días malos bajan de 39,2 % a 36,6 % y el reporte de drift marca 9 de 17 columnas entre 2015 y 2016. Ver [`docs/politica-de-reentrenamiento.md`](docs/politica-de-reentrenamiento.md).
- **La comparación no usa exactamente las mismas filas.** La línea base no puede predecir cuando falta el PM2.5 de hoy; el modelo sí, porque imputa. Son menos del 1 % de las filas.
- **La mejora es moderada.** Buena parte de la señal ya está en el PM2.5 de hoy.
- **Solo usa datos de hoy.** No incluye pronóstico meteorológico de mañana, así que le cuesta anticipar cambios bruscos por viento o lluvia.
- **Las 12 estaciones no son independientes** (correlación diaria mínima de 0,88): cuando el modelo falla un día, suele fallar en varias estaciones a la vez.
- **El umbral de 0,5 no se ha ajustado** y aún no se ha fijado una precisión mínima.
- **Unidades asumidas.** La fuente no declara las unidades; se asumen µg/m³ (ver la dataset card).

## Cómo ejecutarlo

Requisitos: [Git](https://git-scm.com/) y [uv](https://docs.astral.sh/uv/). `uv` instala Python 3.12 por su cuenta.

**Flujo mínimo** (de cero a una predicción):

```
git clone https://github.com/ValentinaRestrepo2/Proyecto_1_Esp_Data.git
cd Proyecto_1_Esp_Data
make setup                          # instala dependencias desde uv.lock
make train                          # descarga los datos y entrena; deja un CANDIDATO
make promote APROBADOR=tu-nombre    # sin este paso no hay modelo vigente y la API responde 503
make test                           # pruebas
make api                            # API en http://127.0.0.1:8000/docs (o `make app` para Streamlit)
```

`make train` solo registra un candidato; `make promote` lo pasa por la compuerta y, si cumple las reglas, lo deja como modelo vigente (ver [Registro de modelos y promoción](#registro-de-modelos-y-promoción)). El tiempo de `make setup` y de la descarga depende de la red.

**Todos los comandos:**

```
make setup      # instala dependencias desde uv.lock
make data       # descarga y une los datos (unos 34 MB, no se versionan)
make smoke      # diagnostica el entorno: sale con código 1 si algo falta
make train      # entrena y registra un CANDIDATO en MLflow (descarga los datos si faltan)
make promote APROBADOR=tu-nombre   # la compuerta decide si el candidato pasa a ser el modelo vigente
make model-card # regenera docs/model-card.md desde los reportes
make test       # pruebas
make app        # abre la app de Streamlit (necesita un modelo vigente: make train y make promote)
make api        # levanta la API (necesita un modelo vigente); documentación en http://127.0.0.1:8000/docs
make mlflow-ui  # interfaz de MLflow para comparar corridas y ver el registro
make drift      # genera el reporte de drift en reports/
make pipeline   # corre el pipeline completo (Prefect) de punta a punta
```

**En Windows no hay `make` por defecto.** Cada comando tiene su equivalente directo:

| `make` | Equivalente |
|---|---|
| `make setup` | `uv sync` |
| `make data` | `uv run python -m proyecto_1_esp_data.data.download` |
| `make smoke` | `uv run python -m proyecto_1_esp_data.smoke` |
| `make train` | `uv run python -m proyecto_1_esp_data.train` |
| `make promote APROBADOR=nombre` | `uv run python -m proyecto_1_esp_data.promocion --aprobador nombre` |
| `make model-card` | `uv run python -m proyecto_1_esp_data.model_card` |
| `make mlflow-ui` | `uv run mlflow ui --backend-store-uri sqlite:///mlflow.db` |
| `make test` | `uv run pytest` |
| `make app` | `uv run streamlit run app/streamlit_app.py` |
| `make api` | `uv run uvicorn app.api_fastapi:app --reload` |
| `make lint` | `uv run ruff check .` |
| `make drift` | `uv run python -m proyecto_1_esp_data.monitoring.drift` |
| `make drift-check` | `uv run python -m proyecto_1_esp_data.monitoring.drift --check` |
| `make pipeline` | `uv run python -m proyecto_1_esp_data.pipeline.flow` |
| `make pipeline-cache` | `uv run python -m proyecto_1_esp_data.pipeline.flow --medir-cache` |
| `make serve` | `uv run python -m proyecto_1_esp_data.pipeline.flow --servir` |

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
  smoke.py             diagnóstico del entorno
  data/download.py     descarga reproducible con hash
  data/contract.py     contrato de datos (rangos, relaciones, volumen)
  data/prepare.py      tabla diaria, target, split temporal y línea base
  features.py          variables de entrada y preprocesamiento
  model.py             pipeline: preprocesamiento + LightGBM
  train.py             entrena y registra un candidato en MLflow (no promueve)
  registro.py          conexión al registro de MLflow, alias y lectura de métricas
  promocion.py         compuerta de promoción y rollback
  model_card.py        genera docs/model-card.md desde los reportes
  predict.py           carga el modelo vigente (alias champion) y predice
  pipeline/flow.py     pipeline de Prefect (reintentos, caché, schedule)
  pipeline/entrenadores.py  un entrenador por modelo: línea base y LightGBM
  monitoring/drift.py  reporte de drift con Evidently
app/                   API (FastAPI) y app (Streamlit)
tests/                 pruebas (datos, modelo, registro, API, monitoreo, notebooks, smoke)
notebooks/01_eda.ipynb análisis exploratorio (sin salidas)
docs/                  model card, contrato de la API, dataset card, política, riesgos, ADRs
reports/               reporte de drift, candidato del pipeline e historial de promociones
```

## Pipeline

`make pipeline` corre de punta a punta: descarga (si falta) → carga → contrato crudo → tabla diaria → contrato procesado → drift → split → entrenar → evaluar → registrar candidato.

- **Reintentos:** solo en la descarga (la única tarea con red), 3 intentos con espera exponencial de 10 s, 20 s, 40 s y jitter. Solo se reintentan errores de red: un hash distinto o un contrato roto no se arreglan reintentando, así que fallan de inmediato.
- **Caché:** en las dos tareas costosas (tabla diaria y drift). La llave combina el hash SHA-256 del CSV, los umbrales de `config.py` y el código fuente del módulo: cambia cualquiera y se recalcula.
- **Caché medido** (`make pipeline-cache`, datos reales, en un portátil con Windows): primera ejecución 10,6 s, segunda 3,77 s, aceleración de unas **2,8 veces**. Recalcular en otra máquina da otros segundos; lo que se conserva es la proporción.
- **Artifacts:** tabla de métricas (modelo y línea base, en validación y producción) y resumen de drift, visibles en la interfaz de Prefect.
- **Schedule:** `make serve` deja el flujo corriendo con el deployment `calidad-aire-trimestral` (cron `0 6 1 1,4,7,10 *`, zona `America/Bogota`): una vez por trimestre, igual que la política de reentrenamiento.
- **No promueve.** Registra `reports/candidato.json` con `promovido: false`. El modelo vigente solo lo cambia la compuerta de promoción (ver la sección siguiente).
- El modelo se elige con `--modelo`: `baseline` ("mañana = hoy", el valor por defecto) o `lightgbm`. Para registrar el modelo real: `uv run python -m proyecto_1_esp_data.pipeline.flow --modelo lightgbm`. Otro modelo se agrega con una función en `pipeline/entrenadores.py`.

## Registro de modelos y promoción

El registro es **MLflow local** (base `mlflow.db` y carpeta `mlruns/`, ignoradas por Git; ver [ADR 004](docs/adr/004-mlflow-local-y-compuerta.md)). El camino de un modelo es siempre el mismo:

```
make train                          # registra un candidato (alias candidate): parámetros, métricas, hash de datos, firma
make promote APROBADOR=tu-nombre    # la compuerta lo compara y, si cumple, mueve el alias champion
make mlflow-ui                      # abre la interfaz para ver y comparar corridas (http://127.0.0.1:5000)
```

- `make train` **nunca** cambia el modelo vigente. El modelo registrado es el pipeline completo (el preprocesamiento va dentro del artefacto).
- La compuerta promueve solo si el candidato supera a la línea base en sensibilidad (en validación y en producción simulada), alcanza la precisión mínima (`PRECISION_MINIMA`, 0,60, valor inicial) y supera estrictamente al modelo vigente.
- Cada decisión, aprobada o rechazada, queda en [`reports/promociones.json`](reports/promociones.json) con las reglas evaluadas, las métricas y quién la tomó, y en las etiquetas de la versión en MLflow.
- **Rollback:** `uv run python -m proyecto_1_esp_data.promocion --aprobador tu-nombre --volver-a <versión>`.
- La API y la app cargan `models:/clasificador_pm25@champion`; `/health` informa la `version_modelo` que están sirviendo. Sin modelo vigente, la API responde 503.

## Contenedor (Docker)

La imagen se construye con el `Dockerfile` (multi-stage, usuario sin root, healthcheck). Durante el build descarga los datos, entrena y pasa el candidato por la compuerta de promoción: si la compuerta lo rechaza, el build falla y no queda una imagen con un modelo no aprobado.

```bash
docker build -t calidad-aire .
docker run --rm -p 8000:8000 calidad-aire
# en otra terminal:
curl http://localhost:8000/health
```

El build necesita internet (descarga el dataset de UCI y verifica su hash). Para cambiar quién figura como aprobador en el historial: `docker build --build-arg APROBADOR=su_nombre -t calidad-aire .`

## Monitoreo

`make drift` compara dos ventanas reales de 12 meses (2015 contra 2016) con Evidently. `make drift-check` termina con código de salida 1 si hay drift y 0 si no. Con 2015 contra 2016 sale con 1 (9 de 17 columnas); con dos años tranquilos (2013-14 contra 2014-15) sale con 0.

El drift es una **alerta para revisar**, no reentrena nada por sí solo. Ver [`docs/politica-de-reentrenamiento.md`](docs/politica-de-reentrenamiento.md) y [`docs/riesgos.md`](docs/riesgos.md).

## Calidad del código

```
uv run pre-commit install        # una vez; revisa ruff, notebooks, secretos y archivos grandes en cada commit
make check                       # ruff + pruebas
```

Los notebooks se guardan **sin salidas** (una prueba falla si no).

## Documentación

- [`docs/model-card.md`](docs/model-card.md): ficha del modelo (uso previsto, rendimiento, aprobación y límites). Se regenera con `make model-card`.
- [`docs/api-contract.md`](docs/api-contract.md): contrato de la API (entradas, respuestas y errores).
- [`docs/dataset-card.md`](docs/dataset-card.md): procedencia, licencia, nulos, límites y riesgos de fuga de datos.
- [`docs/politica-de-reentrenamiento.md`](docs/politica-de-reentrenamiento.md): señales, umbrales y quién decide.
- [`docs/riesgos.md`](docs/riesgos.md): riesgos técnicos y de uso.
- [`docs/adr/000-stack.md`](docs/adr/000-stack.md): por qué este stack.
- [`docs/adr/001-python-312.md`](docs/adr/001-python-312.md): decisión revertida (Python 3.15 a 3.12).
- [`docs/adr/002-prefect.md`](docs/adr/002-prefect.md): cómo y por qué se orquesta con Prefect.
- [`docs/adr/003-joblib-en-vez-de-mlflow.md`](docs/adr/003-joblib-en-vez-de-mlflow.md): decisión revertida (joblib en lugar de MLflow).
- [`docs/adr/004-mlflow-local-y-compuerta.md`](docs/adr/004-mlflow-local-y-compuerta.md): MLflow local y compuerta de promoción; qué falló con el ADR 003.

## Estado y pendientes

Lo que no está hecho todavía, dicho con su motivo:

| Pendiente | Motivo |
|---|---|
| Búsqueda estructurada de hiperparámetros | Hoy cada `make train` es una corrida comparable; no hay una búsqueda con 20 o más corridas anidadas |
| Confirmar `PRECISION_MINIMA` | 0,60 es un valor inicial entre la línea base y LightGBM; el equipo debe confirmarlo |
| Unidades de los contaminantes | La ficha de UCI no las declara; en la dataset card se asumen µg/m³ por la escala observada y está marcado |
