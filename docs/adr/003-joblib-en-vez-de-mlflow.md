# ADR 003: Guardar el modelo con joblib en lugar de MLflow

- **Estado:** aceptada (2026-11-22), con aprobación del equipo. **Reemplaza** la fila "Tracking y registro" del [ADR 000](000-stack.md).
- **Relacionadas:** [ADR 000](000-stack.md), [ADR 001](001-python-312.md), [política de reentrenamiento](../politica-de-reentrenamiento.md), [riesgos](../riesgos.md).

## Contexto

El ADR 000 eligió **MLflow** para el tracking de experimentos y el registro de modelos, con un alias `@champion` para marcar el modelo vigente, y lo dejó en estado "pendiente". La política de reentrenamiento y la matriz de riesgos se escribieron suponiendo ese registro.

Mientras tanto, el modelo se implementó por otro camino, que hoy es el que funciona de punta a punta:

- `train.py` entrena el pipeline completo (preprocesador + LightGBM) solo con la partición de train y lo guarda con **joblib** en `models/clasificador_pm25.joblib`.
- `predict.py` carga ese archivo una sola vez y lo deja en memoria.
- La app de Streamlit y la API de FastAPI usan `predict.py`, así que ninguna de las dos necesita un registro de modelos.
- `make train` reproduce el modelo y sus métricas desde cero: datos verificados por hash, split con fechas fijas y semilla fija en `config.py`.

La rúbrica del módulo exige un modelo reproducible (`make setup && make train && make test`) y al menos un entregable servido. MLflow aparece en los recursos del curso como algo opcional ("si quieres añadir tracking de experimentos"), no como requisito.

## Decisión

- **No usar MLflow por ahora.** El modelo vigente es el archivo `models/clasificador_pm25.joblib`, que no se versiona en Git y se regenera con `make train`.
- **Las métricas del modelo** se muestran al correr `make train` y quedan documentadas en el README (sección "Resultados"), junto a las de la línea base.
- **La comparación entre modelos** se hace de forma manual, en el README y en el Pull Request que introduce cada cambio.

## Por qué

- **Sigue el criterio del ADR 000:** cubrir lo que pide la rúbrica con el menor número de piezas, y que cada pieza se instale y corra con un comando en una máquina limpia. MLflow es una pieza más que puede fallar.
- **Dependencias:** como ya se vio en el ADR 001, MLflow trae una cadena larga de dependencias, con el mismo riesgo de problemas en Windows que obligó a bajar a Python 3.12.
- **Lo que aporta MLflow no lo usamos hoy:** con un solo modelo candidato (LightGBM) y una sola configuración, el historial de experimentos y la interfaz de comparación tienen poco que mostrar.
- **Tiempo:** el equipo prioriza que lo exigido (pruebas, `make train`, app y resultados) esté completo y en verde.

## Alternativas consideradas

- **MLflow local** (carpeta `mlruns/`, sin servidor): da historial y registro con alias, pero agrega la dependencia, una carpeta más que ignorar en Git y cambios en `train.py` y `predict.py`. Descartada por ahora; es la opción natural si se retoma.
- **MLflow con servidor de tracking:** exige levantar y mantener un servicio. Descartada, por el mismo motivo por el que se descartó Airflow en el ADR 000.
- **Versionar el modelo en Git:** el `.gitignore` excluye los modelos a propósito; además, el modelo se puede regenerar. Descartada.

## Consecuencias

Lo que se pierde, dicho de forma explícita:

- **No hay historial automático de experimentos.** Cada `make train` sobrescribe el modelo anterior, y las métricas de entrenamientos pasados solo quedan si alguien las escribe.
- **No existe el alias `@champion`.** La política de reentrenamiento (secciones 4 y 5), la matriz de riesgos (riesgo 12) y el README (sección "Pipeline") deben dejar de mencionarlo y describir la promoción y el `rollback` con archivos.
- **`make train` reemplaza el modelo vigente sin revisión.** Esto contradice el principio de la política de que ningún paso automático promueve un modelo. Queda como pendiente: guardar cada entrenamiento con fecha y huella de datos, y que la promoción sea copiar a mano el candidato aprobado a `models/clasificador_pm25.joblib`.
- **No se registran métricas por estación del modelo;** solo existen para la línea base, en `reports/candidato.json`.

## Condición para revisar esta decisión

Volver a MLflow si ocurre alguna de estas condiciones:

- La rúbrica que se está siguiendo exige tracking o registro de modelos.
- Se agregan más modelos o búsquedas de hiperparámetros, y la comparación manual en el README deja de ser práctica.

El cambio estaría acotado a `train.py`, para registrar parámetros, métricas y el modelo, y a `predict.py`, para cargar el modelo desde el registro. La app, la API y las pruebas no tendrían que cambiar.
