# ADR 000: Stack tecnológico

- **Estado:** aceptada (2026-11-08). Las piezas marcadas "pendiente" están decididas, pero aún no implementadas en el repositorio.
- **Relacionadas:** [ADR 001](001-python-312.md), que revierte la versión de Python elegida al inicio.

## Contexto

El proyecto predice si mañana el PM2.5 de una estación de Beijing superará 75 µg/m³. La rúbrica evalúa el ciclo de vida (reproducibilidad, datos, tracking, pipeline, deployment, monitoreo) y no la calidad del modelo. Somos tres personas con poco tiempo y varias de las herramientas eran nuevas para el equipo. El criterio de elección fue: **cubrir las siete dimensiones con el menor número de piezas posible**, y que cada pieza se pueda instalar y ejecutar desde cero con un comando.

## Decisión

| Necesidad | Elección | Estado |
|---|---|---|
| Entorno y dependencias | **uv** con `uv.lock` y Python 3.12 | En uso |
| Datos | **pandas 2.x** (`<3`, ver ADR 001) | En uso |
| Modelo | **scikit-learn** para la línea base y el preprocesamiento, **LightGBM** para el modelo candidato | LightGBM pendiente de entrenar |
| Tracking y registro | **MLflow**, con alias (`@champion`) y no con `stages` | Pendiente |
| Orquestación | **Prefect** | Pendiente |
| Servicio | **FastAPI** + **Docker** | Pendiente |
| Monitoreo de drift | **Evidently 0.7** | En uso |
| Calidad | **ruff**, **pytest**, **pre-commit** (ruff, nbstripout, gitleaks) y CI en GitHub Actions | En uso |

## Alternativas consideradas

- **pip + requirements.txt:** más conocido, pero sin lockfile con hashes ni gestión de la versión de Python. Descartada: la reproducibilidad es una dimensión de la rúbrica.
- **Airflow en lugar de Prefect:** más potente, pero exige un servidor y una base de datos para un pipeline de pocos pasos. Descartada por costo de instalación frente al beneficio.
- **Un modelo más complejo o una búsqueda de hiperparámetros extensa:** la calidad del modelo no puntúa. Se usa LightGBM con una búsqueda pequeña y comparable en MLflow.
- **Kubernetes, feature store o un segundo orquestador:** **no se usan a propósito.** El problema es un proceso por lotes diario sobre un CSV de 34 MB; `docker compose` alcanza y cada pieza adicional es una pieza más que puede fallar en una máquina limpia.
- **Drift calculado a mano con numpy:** descartada. Evidently trae las pruebas estadísticas, el reporte HTML y la comparación de ventanas reales ya probados.

## Consecuencias

- Una persona nueva clona el repositorio y corre `make setup`, `make data` y `make smoke` para tener el entorno validado.
- Hay que mantener `uv.lock` actualizado y commiteado.
- Evidently condiciona la versión de pandas (ADR 001): al actualizar pandas hay que volver a verificar que Evidently se importe.
- Como MLflow, Prefect y Docker aún no están implementados, el README lista esos pendientes con su motivo. El resto del proyecto (datos, contrato, split, línea base, drift) ya funciona de forma independiente.
