# Ficha del modelo: clasificador de mala calidad del aire en Beijing

> Generada con `make model-card` a partir de `reports/candidato.json` y
> `reports/promociones.json`. No se edita a mano: se regenera.

## 1. Resumen

| Campo | Valor |
|---|---|
| Nombre en el registro | `clasificador_pm25` (MLflow, alias `champion`) |
| Versión vigente | 1 |
| Aprobada por | Santiago el 2026-11-24 (UTC) |
| Algoritmo | LightGBM dentro de un pipeline de scikit-learn (imputación, escalado y one-hot) |
| Tarea | Clasificación binaria por estación y día |
| Target | PM2.5 medio de **mañana** > 75 µg/m³ |
| Huella de los datos (SHA-256) | `e63a369c2ac0a5667225b0c8b3d92cd367c04a295790a0f496ae0c32b2ece1b7` |
| Semilla | 42 |

## 2. Uso previsto

- **Para qué sirve:** estimar, con los datos de hoy de una estación, la probabilidad de que mañana
  el promedio diario de PM2.5 supere 75 µg/m³, como ayuda para avisar
  con anticipación a quien deba planear actividades al aire libre.
- **Quién lo usa:** personas que revisan la predicción junto con los datos oficiales de calidad
  del aire. Es una ayuda para decidir, no una decisión automática.
- **Dónde aplica:** las 12 estaciones de Beijing del dataset, con datos horarios de 2013 a 2017.

## 3. Fuera de alcance

- Otras ciudades u otras épocas: no se evaluó fuera de Beijing ni después de febrero de 2017.
- Como única fuente para decisiones de salud pública. No sustituye a las mediciones oficiales.
- Pronóstico de contaminantes distintos del PM2.5 o de horizontes distintos a "mañana".

## 4. Datos

- Fuente: UCI, Beijing Multi-Site Air Quality (dataset 501), licencia CC BY 4.0. Detalle en
  [`dataset-card.md`](dataset-card.md).
- Split temporal con fechas fijas, sin mezcla aleatoria:

| Partición | Periodo |
|---|---|
| Entrenamiento | 2013-03-01 a 2014-12-31 |
| Validación | 2015-01-01 a 2015-12-31 |
| Producción simulada | 2016-01-01 a 2017-02-28 |

- El modelo se ajusta solo con entrenamiento. La imputación y el escalado también.
- Variables de entrada: 13 numéricas (contaminantes, meteorología y PM2.5 de ayer y antier) y 3
  categóricas (dirección del viento, estación y estación del año).

## 5. Rendimiento

La métrica principal es la **sensibilidad**: no avisar un día malo es el error más costoso. La
línea base es "mañana = hoy".

| Partición | Modelo | Sensibilidad | Precisión | F1 |
|---|---|---|---|---|
| Validación (2015) | Línea base | 0,641 | 0,643 | 0,642 |
| Validación (2015) | **Modelo** | 0,739 | 0,684 | 0,711 |
| Producción simulada (2016-01 a 2017-02) | Línea base | 0,591 | 0,588 | 0,589 |
| Producción simulada (2016-01 a 2017-02) | **Modelo** | 0,647 | 0,611 | 0,628 |

Hiperparámetros: 300 árboles, tasa de aprendizaje 0,05,
31 hojas, `class_weight="balanced"`, umbral de decisión
0,5.

### Por estación (validación 2015, de menor a mayor sensibilidad)

| Estación | Sensibilidad | Precisión | Días evaluados |
|---|---|---|---|
| Huairou | 0,562 | 0,709 | 363 |
| Changping | 0,598 | 0,676 | 353 |
| Dingling | 0,691 | 0,618 | 363 |
| Gucheng | 0,725 | 0,610 | 360 |
| Shunyi | 0,755 | 0,708 | 364 |
| Tiantan | 0,755 | 0,703 | 363 |
| Wanshouxigong | 0,761 | 0,671 | 361 |
| Dongsi | 0,765 | 0,727 | 362 |
| Nongzhanguan | 0,773 | 0,682 | 356 |
| Guanyuan | 0,796 | 0,736 | 363 |
| Aotizhongxin | 0,797 | 0,702 | 358 |
| Wanliu | 0,836 | 0,667 | 360 |

Cada estación tiene unos 360 días evaluados, así que cada cifra tiene un margen de error
aproximado de ±8 puntos. Las estaciones con menor sensibilidad, al inicio de la tabla, son las
que pueden no mejorar a la línea base; ver limitaciones.

## 6. Cómo se aprobó

Antes de servir el modelo pasó por la compuerta de promoción (`make promote`):

- Cumple: Sensibilidad en val supera a la línea base (candidato 0.739 frente a línea base 0.641)
- Cumple: Sensibilidad en produccion supera a la línea base (candidato 0.647 frente a línea base 0.591)
- Cumple: Precisión en val alcanza la mínima (candidato 0.684, mínima 0.600)

Precisión mínima exigida: 0,60 (valor inicial, pendiente de confirmar
por el equipo). El historial completo tiene 2 decisiones, 1 de ellas rechazos (`reports/promociones.json`). Detalle de la política en
[`politica-de-reentrenamiento.md`](politica-de-reentrenamiento.md) y de la decisión en el
[ADR 004](adr/004-mlflow-local-y-compuerta.md).

## 7. Limitaciones y riesgos

- **No mejora en todas las estaciones.** En Huairou la sensibilidad queda por debajo de la línea
  base y en Changping empata. La causa no se ha investigado.
- **Pierde rendimiento con el tiempo.** La sensibilidad baja de validación a producción
  (0,74 a 0,65) y el reporte de
  drift marca cambios en varias columnas entre 2015 y 2016.
- **Solo usa datos de hoy.** No incluye pronóstico meteorológico de mañana, por lo que le cuesta
  anticipar cambios bruscos por viento o lluvia.
- **Estaciones correlacionadas.** Cuando falla un día, suele fallar en varias estaciones a la vez.
- **Umbral sin ajustar.** El umbral de decisión (0,5) no se optimizó.
- **Unidades asumidas.** La fuente no declara unidades; se asumen µg/m³.
- Registro completo de riesgos en [`riesgos.md`](riesgos.md).

## 8. Cómo reproducirlo y mantenerlo

```
make data          # descarga y verifica el hash
make train         # entrena y registra un candidato (no lo promueve)
make promote APROBADOR=<nombre>
make model-card    # regenera esta ficha
```

Reentrenamiento: ver [`politica-de-reentrenamiento.md`](politica-de-reentrenamiento.md). El
rollback se hace moviendo el alias `champion` a una versión anterior
(`--volver-a VERSION`).
