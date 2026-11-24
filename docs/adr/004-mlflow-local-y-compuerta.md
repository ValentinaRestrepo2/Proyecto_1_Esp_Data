# ADR 004: MLflow local y compuerta de promoción (revierte el ADR 003)

- **Estado:** aceptada (2026-11-23). **Revierte** el [ADR 003](003-joblib-en-vez-de-mlflow.md) y vuelve a la decisión del [ADR 000](000-stack.md) sobre tracking y registro.
- **Relacionadas:** [ADR 000](000-stack.md), [ADR 003](003-joblib-en-vez-de-mlflow.md), [política de reentrenamiento](../politica-de-reentrenamiento.md), [riesgos](../riesgos.md).

## Contexto

El ADR 003 (2026-11-22) dejó el modelo en un archivo `models/clasificador_pm25.joblib` y descartó MLflow por simplicidad. Dos días después, al contrastar el repositorio con la rúbrica del instructor, apareció lo que había salido mal:

- **La rúbrica sí exige tracking y registro.** La dimensión "Tracking y registry" (15 %) toma como evidencia la interfaz de MLflow y su nivel 1 describe exactamente nuestra situación: métricas en `print` y un archivo de modelo sin forma de saber qué datos ni parámetros lo produjeron. El ADR 003 había supuesto que MLflow era opcional; su propia "condición para revisar esta decisión" (la rúbrica exige tracking o registro) se cumplía.
- **`make train` promovía sin revisión.** Sobrescribía el modelo que sirven la API y la app. Era una contradicción con la política de reentrenamiento (ninguna señal ni paso automático promueve) y con la rúbrica, que penaliza la auto-promoción sin compuerta.
- **No había historial.** Cada entrenamiento borraba el anterior: no se podía comparar ni volver atrás.

**Qué se aprendió:** una decisión de "simplificar" una pieza debe contrastarse primero con el criterio de evaluación; ahorrar una dependencia salió más caro que instalarla. El ADR 003 se conserva como historia, no se borra.

## Decisión

1. **MLflow local, sin servidor:** base SQLite `mlflow.db` y carpeta `mlruns/` en la raíz (ignoradas por Git). Se puede apuntar a otra con `MLFLOW_TRACKING_URI`.
2. **`make train` solo registra un candidato.** Una corrida con parámetros (hiperparámetros, semilla, fechas del split, hash de los datos), métricas del modelo **y de la línea base** en validación y producción simulada, firma y ejemplo de entrada. El modelo registrado es el pipeline completo (el preprocesamiento va **dentro** del artefacto) y queda con el alias `candidate`. No toca el modelo vigente.
3. **Una compuerta separada decide la promoción** (`promocion.py`, `make promote`). Mueve el alias `champion` solo si el candidato: (a) supera a la línea base en sensibilidad en validación y en producción simulada, (b) alcanza `PRECISION_MINIMA` en validación y (c) supera estrictamente al vigente. Cada decisión, aprobada o rechazada, queda en `reports/promociones.json` y en las etiquetas de la versión (`validation_status`, `decidido_por`, `razones_de_rechazo`).
4. **Alias, no `stages`** (deprecados). El rollback mueve `champion` a una versión anterior (`--volver-a`), sin reentrenar.
5. **La API y la app cargan por alias** (`models:/clasificador_pm25@champion`), no un archivo copiado, y `/health` informa la versión del modelo que están sirviendo.
6. **Formato `cloudpickle` para guardar el modelo.** El formato por defecto de MLflow (`skops`) exige declarar cada tipo de LightGBM como confiable. Solo se cargan modelos de nuestro propio registro, nunca de terceros.

## Alternativas consideradas

- **Seguir con joblib y copiar archivos a mano:** es lo que dejó el ADR 003. Descartada por los tres problemas del contexto.
- **MLflow con servidor de tracking:** exige levantar y mantener un servicio para un solo equipo. Descartada, por el mismo motivo por el que se descartó Airflow en el ADR 000.
- **Almacén de archivos de MLflow (`mlruns/` sin base de datos):** su soporte de registro y alias está en desuso. Se usa SQLite, que no necesita instalar nada.
- **`PRECISION_MINIMA` calculada de los datos:** descartada; es una decisión de negocio (cuántas falsas alarmas se toleran) y se fija a mano en `config.py`.

## Consecuencias

- **Hay que entrenar y promover una vez para tener modelo vigente:** `make train` y luego `make promote`. Sin eso, la API responde 503 con un mensaje fijo y la app avisa.
- **El registro no se versiona.** `mlflow.db` y `mlruns/` se regeneran con `make train`; lo que sí queda en Git es el historial de decisiones (`reports/promociones.json`).
- **Un contenedor necesita el registro:** o se entrena y promueve dentro de la imagen, o se monta el registro en tiempo de ejecución.
- **`PRECISION_MINIMA = 0,60` es un valor inicial** (entre la línea base, 0,643, y LightGBM, 0,684, en validación). El equipo debe confirmarlo.
- **No se hizo una búsqueda estructurada de hiperparámetros** (el nivel 5 pide al menos 20 corridas comparables); hoy cada `make train` es una corrida comparable a las anteriores.
- **MLflow añade dependencias** (el mismo riesgo del ADR 001 con las versiones). Se instaló sin cambiar las de FastAPI, pandas ni Prefect, y está fijado en `uv.lock`.
