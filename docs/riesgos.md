# Riesgos del proyecto

Riesgos técnicos y de uso del sistema que predice si **mañana el PM2.5 promedio superará 75 µg/m³** en una estación de Beijing. Probabilidad e impacto en escala Baja / Media / Alta.

| # | Riesgo | Prob. | Impacto | Mitigación | Estado |
|---|---|---|---|---|---|
| 1 | **Fuga de datos** que haga ver al modelo mejor de lo que es (split aleatorio, preprocesamiento con todo el dataset, mismo día repartido entre particiones) | Media | Alta | Split temporal con fechas fijas (`config.py`); target de cada partición dentro de ella; imputadores y escaladores ajustados solo con train; pruebas del split. Ver `docs/dataset-card.md`, sección 7 | Mitigado |
| 2 | **Falsos negativos**: no avisar un día de contaminación alta. Es el error más costoso, porque las personas podrían exponerse sin saberlo | Media | Alta | La métrica principal es la sensibilidad; se exige precisión mínima para no generar alertas inútiles; se reporta por estación | Mitigado (en seguimiento) |
| 3 | **Drift de datos**: el aire cambia con el tiempo y el modelo envejece. Ya se midió: la sensibilidad de la línea base cayó de 0,637 a 0,585 entre 2015 y 2016 | Alta | Media | Reporte con Evidently trimestral; alertas revisadas por una persona; renovación a los 12 meses. Ver `docs/politica-de-reentrenamiento.md` | Activo |
| 4 | **Falsas alarmas por drift**: la alerta salta por cambios reales y buenos (menos SO2) o por ruido; entre años consecutivos la proporción de columnas con drift varió de 0,18 a 0,65 | Alta | Baja | El drift no reentrena por sí solo; manda el rendimiento. Umbral documentado | Aceptado |
| 5 | **Desbalance de clases que cambia**: días malos de 43,6 % (train) a 36,6 % (producción) | Alta | Media | Se vigila la proporción de días malos; se evalúa con PR-AUC además de sensibilidad | Activo |
| 6 | **Cobertura limitada**: una sola ciudad y 4 años. El modelo no se generaliza a otras ciudades ni a épocas con otras políticas ambientales | Alta | Media | Declarado en la dataset card; no se promete uso fuera de Beijing | Aceptado |
| 7 | **Sesgo por estación**: las estaciones difieren (31,7 % a 43,5 % de días malos) y el modelo podría rendir peor en alguna | Media | Media | Métricas por estación, no solo el total. Las 12 estaciones están muy correlacionadas, así que el total es optimista | Mitigado |
| 8 | **Datos erróneos del sensor**: valores tope de 999, PM10 menor que PM2.5 en ~5 % de las filas, huecos de hasta 343 horas | Media | Media | Contrato de datos con rangos y tolerancias; día válido con 18 horas o más; relleno máximo de 3 horas | Mitigado |
| 9 | **La fuente cambia o desaparece** (UCI actualiza el archivo o lo retira) | Baja | Alta | Hash SHA-256 del ZIP en `data/raw/metadata.json`: si cambia, la descarga falla en vez de usar datos distintos sin avisar | Mitigado |
| 10 | **Licencia**: uso fuera de lo permitido | Baja | Media | CC BY 4.0: se cita la fuente (UCI, Song Chen, DOI 10.24432/C5RK5G) | Mitigado |
| 11 | **Versiones de librerías**: Python 3.15 no tenía versiones listas (pyyaml); Evidently 0.7.23 se rompe al importarse con pandas 3 | Alta | Media | Proyecto en Python 3.12 y `pandas<3`, verificado con pruebas y CI. Revisar cuando Evidently publique soporte para pandas 3 | Mitigado (con deuda) |
| 12 | **Promoción automática de un modelo malo** | Baja | Alta | La promoción es manual: se mueve el alias `@champion` tras revisar la comparación; se conserva el modelo anterior | Mitigado |
| 13 | **Secretos o datos pesados en el repositorio** | Baja | Media | `.gitignore` excluye los datos crudos; solo se versiona `metadata.json`; el CSV de unos 34 MB nunca se sube | Mitigado |
| 14 | **Uso indebido de la predicción** como decisión de salud pública única | Media | Alta | Es una ayuda para decidir, no un reemplazo de los datos oficiales de calidad del aire; el modelo no se evalúa por calidad predictiva en esta entrega | Aceptado |

## Qué no cubre este análisis
- No se estimó el costo económico ni de salud de un falso negativo; solo se priorizó la sensibilidad por criterio.
- El drift se calculó entre 2015 y 2016 sobre datos reales; no hay datos posteriores a febrero de 2017.
