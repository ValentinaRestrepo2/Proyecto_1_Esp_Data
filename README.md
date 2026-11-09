# Predicción de días con mala calidad del aire en Beijing

Proyecto final de MLOps (Universidad de Medellín). Predice, para cada estación de monitoreo, si **mañana el promedio de PM2.5 superará 75 µg/m³**, con datos horarios reales de 12 estaciones de Beijing (2013-2017).

El foco del proyecto es el **ciclo de vida** (datos validados, split sin fuga, monitoreo de drift, trazabilidad), no la calidad del modelo.

## El problema

- **Tarea:** clasificación binaria por estación y día.
- **Target:** `PM2.5 medio de mañana > 75 µg/m³` (`UMBRAL_PM25` en `config.py`).
- **Métrica principal:** sensibilidad (no avisar un día malo es el error más costoso), con precisión mínima, F1 y PR-AUC de apoyo.
- **Línea base:** "mañana = hoy". Sensibilidad de **0,64** en validación y **0,59** en producción simulada. Es el número a superar.
- **Datos:** [Beijing Multi-Site Air Quality](https://archive.ics.uci.edu/dataset/501) (UCI), licencia CC BY 4.0. Detalles en [`docs/dataset-card.md`](docs/dataset-card.md).

## Cómo ejecutarlo

Requisitos: [Git](https://git-scm.com/) y [uv](https://docs.astral.sh/uv/). `uv` instala Python 3.12 por su cuenta.

```
git clone https://github.com/ValentinaRestrepo2/Proyecto_1_Esp_Data.git
cd Proyecto_1_Esp_Data
make setup      # instala dependencias desde uv.lock
make data       # descarga y une los datos (unos 34 MB, no se versionan)
make smoke      # diagnostica el entorno: sale con código 1 si algo falta
make test       # pruebas
make drift      # genera el reporte de drift en reports/
```

**En Windows no hay `make` por defecto.** Cada comando tiene su equivalente directo:

| `make` | Equivalente |
|---|---|
| `make setup` | `uv sync` |
| `make data` | `uv run python -m proyecto_1_esp_data.data.download` |
| `make smoke` | `uv run python -m proyecto_1_esp_data.smoke` |
| `make test` | `uv run pytest` |
| `make lint` | `uv run ruff check .` |
| `make drift` | `uv run python -m proyecto_1_esp_data.monitoring.drift` |
| `make drift-check` | `uv run python -m proyecto_1_esp_data.monitoring.drift --check` |

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
  monitoring/drift.py  reporte de drift con Evidently
tests/                 pruebas (datos, monitoreo, notebooks, smoke)
notebooks/01_eda.ipynb análisis exploratorio (sin salidas)
docs/                  dataset card, política de reentrenamiento, riesgos, ADRs
reports/               reporte de drift (HTML) y su resumen (JSON)
```

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

- [`docs/dataset-card.md`](docs/dataset-card.md): procedencia, licencia, nulos, límites y riesgos de fuga de datos.
- [`docs/politica-de-reentrenamiento.md`](docs/politica-de-reentrenamiento.md): señales, umbrales y quién decide.
- [`docs/riesgos.md`](docs/riesgos.md): riesgos técnicos y de uso.
- [`docs/adr/000-stack.md`](docs/adr/000-stack.md): por qué este stack.
- [`docs/adr/001-python-312.md`](docs/adr/001-python-312.md): decisión revertida (Python 3.15 a 3.12).

## Estado y pendientes

Lo que no está hecho todavía, dicho con su motivo:

| Pendiente | Motivo |
|---|---|
| Entrenamiento (`make train`), MLflow, registro de modelos con alias y `docs/model-card.md` | En desarrollo; el Pipeline y la API dependen de que exista un modelo registrado |
| Pipeline con Prefect | Depende del entrenamiento. Las tareas de cargar, validar, preparar y drift ya existen como funciones |
| API (FastAPI), Dockerfile y tests de la API en CI | Depende del modelo registrado |
| Contrato de datos para los datos procesados | Hoy solo se valida el dato crudo |
| Unidades de los contaminantes | La ficha de UCI no las declara; en la dataset card se asumen µg/m³ por la escala observada y está marcado |
