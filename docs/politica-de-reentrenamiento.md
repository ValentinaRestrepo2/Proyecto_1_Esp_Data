# Política de reentrenamiento

Define **cuándo** se revisa el modelo, **qué señales** activan una alerta, **quién decide** y **cómo** se cambia el modelo en producción. Todos los umbrales viven en `src/proyecto_1_esp_data/config.py`.

**Principio central:** ninguna señal reentrena ni promueve un modelo por sí sola. Las señales generan una **alerta**; una persona revisa y decide.

## 1. Qué se monitorea

| Señal | Cómo se mide | Umbral | Frecuencia |
|---|---|---|---|
| Drift de datos | Evidently compara los últimos 12 meses completos contra la ventana de referencia (2015). Métodos fijos: Wasserstein normalizada (numéricas) y Jensen-Shannon (categóricas) | Una columna tiene drift si su distancia es ≥ **0,1** (`DRIFT_UMBRAL_COLUMNA`). Hay drift del dataset si ≥ **50 %** de las columnas lo tiene (`DRIFT_UMBRAL_COMPARTIDO`) | Trimestral |
| Rendimiento | Sensibilidad (métrica principal), precisión y F1 en la ventana reciente, con el target ya observado (se conoce al día siguiente) | Caída de **5 puntos o más** en sensibilidad frente a la validación del modelo vigente | Trimestral |
| Proporción de días malos | % de días sobre 75 µg/m³ en la ventana reciente | Cambio de **5 puntos o más** frente a la referencia | Trimestral |
| Calidad de datos | Contrato de datos (`data/contract.py`) sobre los datos nuevos | **Cualquier** regla incumplida detiene el pipeline | En cada carga (tanto el crudo como la tabla procesada) |

Se usan ventanas de **12 meses completos** porque la contaminación tiene estacionalidad fuerte (diciembre es el peor mes y agosto el mejor); comparar meses sueltos mezclaría estación con cambio real.

## 2. Qué se observó con los datos reales

Reporte generado con `uv run python -m proyecto_1_esp_data.monitoring.drift` (`reports/drift_referencia_vs_actual.html` y `reports/drift_resumen.json`), referencia 2015 contra 2016:

- **Drift detectado en 9 de 17 columnas (52,9 %)**, apenas sobre el umbral de 50 %: CO, PM10, RAIN, SO2, WSPM, pm25, pm25_lag1, pm25_lag2 y wd. La mayor distancia es SO2 (0,22).
- La proporción de días malos baja de 39,3 % a 36,0 %.
- La línea base "mañana = hoy" baja de 0,637 a 0,585 de sensibilidad.
- **Calibración del umbral:** entre años consecutivos de 12 meses la proporción de columnas con drift varió de **0,18 a 0,65** (0,18 / 0,65 / 0,18 entre marzo-febrero de 2013-14, 2014-15, 2015-16 y 2016-17). El drift natural entre años ya es grande y la alerta a 0,5 está cerca del ruido.

**Por qué no se usa un p-valor:** con miles de filas por ventana, una prueba como K-S da `p < 0,05` ante diferencias minúsculas y sin importancia práctica; casi cualquier par de años saldría con drift. Por eso el umbral se pone sobre el **tamaño del efecto** (distancia de Wasserstein normalizada, en unidades de desviación estándar de la referencia, y distancia de Jensen-Shannon), que no crece con el número de filas. Los métodos están fijos en `monitoring/drift.py`: Evidently cambia solo a K-S con p-valor cuando hay menos de 1.000 filas, y eso haría que el umbral significara otra cosa según el tamaño de la muestra.

**Consecuencia de diseño:** el drift de datos es una alerta para investigar, no una razón suficiente para reentrenar. Un contaminante que baja (SO2, CO) puede reflejar una mejora real del aire, no un problema del modelo. Lo que decide es el **rendimiento**.

## 3. Cuándo se reentrena (los `trigger`)

Se abre una revisión cuando ocurre **cualquiera** de estas condiciones:

1. Cae la sensibilidad 5 puntos o más (señal principal).
2. Hay drift del dataset **y** el rendimiento cae al menos 2 puntos (las dos señales juntas).
3. El contrato de datos falla de forma sostenida (por ejemplo, UCI cambia el archivo y el hash no coincide).
4. Pasan **12 meses** sin reentrenar, aunque no haya alertas (renovación mínima, por la estacionalidad).

Si solo hay drift y el rendimiento se mantiene, se documenta y se sigue vigilando; no se reentrena.

## 4. Cómo se reentrena y se promueve

1. El pipeline (`make pipeline`, y cada trimestre el deployment `calidad-aire-trimestral`) entrena un **candidato** con los datos hasta la fecha, reservando los últimos 12 meses como validación y respetando el split temporal (sin mezclar filas).
2. Se compara contra el modelo vigente (`@champion`) en la validación **y** en la ventana reciente, con sensibilidad, precisión mínima, F1 y PR-AUC, además de las métricas por estación.
3. El candidato debe superar al vigente en sensibilidad **sin** bajar de la precisión mínima, y superar la línea base "mañana = hoy".
4. El pipeline deja el candidato en `reports/candidato.json` con `promovido: false`. **La promoción es manual:** una persona del equipo mueve el alias `@champion` en el registro de modelos después de revisar la comparación. Ningún flujo automático promueve modelos.
5. Se conserva el modelo anterior para poder **volver atrás** moviendo el alias de nuevo.

## 5. Aprobación, `rollback` y registro

- **Aprobador:** una persona del equipo distinta de quien entrenó el candidato revisa la comparación y mueve el alias.
- **`Rollback`:** volver al modelo anterior moviendo de nuevo el alias `@champion` a la versión previa, que siempre se conserva. No requiere reentrenar.
- **Qué queda registrado en cada decisión:** el motivo del `trigger` (qué señal saltó y con qué valor), las ventanas de datos usadas, el hash de `data/raw/metadata.json`, las métricas del candidato y del vigente, quién aprobó y la fecha. El resumen `reports/drift_resumen.json` se guarda junto a la corrida.

## 6. Responsables

| Rol | Responsabilidad |
|---|---|
| Datos | Mantener el contrato, el reporte de drift y los umbrales |
| Modelo / pipeline | Entrenar candidatos y mostrar la comparación |
| Revisión (al menos una persona distinta de quien entrenó) | Aprobar la promoción |

## 7. Límites conocidos

- Los umbrales de rendimiento (5 y 2 puntos) son valores iniciales; se confirman cuando exista el modelo y su validación.
- El umbral de drift usa el valor por defecto de Evidently; con solo 4 años de datos no hay base para calibrarlo mejor. Se revisará cuando haya más ventanas.
- Las 12 estaciones se evalúan juntas, pero están muy correlacionadas entre sí (correlación diaria mínima 0,88), así que no son 12 muestras independientes. El rendimiento también se mira por estación.
- La política asume que el target se observa al día siguiente. Si el dato llegara con retraso, el monitoreo de rendimiento se retrasa igual.
