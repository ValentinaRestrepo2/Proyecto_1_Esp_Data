"""Genera la ficha del modelo (`docs/model-card.md`) a partir de los reportes reales.

Las cifras (métricas, parámetros, versión vigente, quién aprobó y cuándo) no se
escriben a mano: salen de `reports/candidato.json` y `reports/promociones.json`.
Así la ficha no puede contradecir lo que realmente se evaluó. El texto sobre uso
previsto y limitaciones sí es redactado y se mantiene en este archivo.

Uso:
    uv run python -m proyecto_1_esp_data.model_card
"""

from __future__ import annotations

import json
from pathlib import Path

from proyecto_1_esp_data import config

DESTINO = Path("docs/model-card.md")


def _n(valor: float, decimales: int = 3) -> str:
    """Número con coma decimal, como en el resto de la documentación."""
    return f"{valor:.{decimales}f}".replace(".", ",")


def _leer(ruta: Path) -> dict | list:
    if not ruta.exists():
        raise FileNotFoundError(
            f"Falta {ruta}. Genera el reporte con `make pipeline` o `make promote`."
        )
    return json.loads(ruta.read_text(encoding="utf-8"))


def _decision_vigente(historial: list[dict]) -> dict:
    """Última decisión aprobada del historial: es el modelo que sirve la API."""
    aprobadas = [e for e in historial if e.get("decision") == "aprobado"]
    if not aprobadas:
        raise LookupError(
            "El historial no tiene ninguna promoción aprobada. "
            "Corre `make train` y `make promote APROBADOR=<nombre>`."
        )
    return aprobadas[-1]


def _fila(particion: str, nombre: str, m: dict) -> str:
    return (
        f"| {particion} | {nombre} | {_n(m['sensibilidad'])} | "
        f"{_n(m['precision'])} | {_n(m['f1'])} |"
    )


def _tabla_estaciones(por_estacion: dict) -> str:
    filas = sorted(por_estacion.items(), key=lambda kv: kv[1]["sensibilidad"])
    lineas = [
        "| Estación | Sensibilidad | Precisión | Días evaluados |",
        "|---|---|---|---|",
    ]
    for nombre, m in filas:
        lineas.append(
            f"| {nombre} | {_n(m['sensibilidad'])} | {_n(m['precision'])} | {int(m['n'])} |"
        )
    return "\n".join(lineas)


def construir(candidato: dict, historial: list[dict]) -> str:
    vigente = _decision_vigente(historial)
    mc = vigente["metricas_candidato"]
    mb = vigente["metricas_linea_base"]
    p = candidato["parametros"]
    rechazos = [e for e in historial if e.get("decision") == "rechazado"]
    fecha = vigente["fecha_utc"][:10]

    filas = "\n".join(
        [
            _fila("Validación (2015)", "Línea base", mb["val"]),
            _fila("Validación (2015)", "**Modelo**", mc["val"]),
            _fila(
                "Producción simulada (2016-01 a 2017-02)",
                "Línea base",
                mb["produccion"],
            ),
            _fila(
                "Producción simulada (2016-01 a 2017-02)",
                "**Modelo**",
                mc["produccion"],
            ),
        ]
    )
    comprobaciones = "\n".join(
        f"- {'Cumple' if c['cumple'] else 'No cumple'}: {c['regla']} ({c['detalle']})"
        for c in vigente["comprobaciones"]
    )
    historial_txt = (
        f"El historial completo tiene {len(historial)} decisiones, "
        f"{len(rechazos)} de ellas rechazos (`reports/promociones.json`)."
    )

    return f"""# Ficha del modelo: clasificador de mala calidad del aire en Beijing

> Generada con `make model-card` a partir de `reports/candidato.json` y
> `reports/promociones.json`. No se edita a mano: se regenera.

## 1. Resumen

| Campo | Valor |
|---|---|
| Nombre en el registro | `{config.MODELO_REGISTRADO}` (MLflow, alias `{config.ALIAS_VIGENTE}`) |
| Versión vigente | {vigente["version"]} |
| Aprobada por | {vigente["decidido_por"]} el {fecha} (UTC) |
| Algoritmo | LightGBM dentro de un pipeline de scikit-learn (imputación, escalado y one-hot) |
| Tarea | Clasificación binaria por estación y día |
| Target | PM2.5 medio de **mañana** > {_n(config.UMBRAL_PM25, 0)} µg/m³ |
| Huella de los datos (SHA-256) | `{vigente["huella_datos_sha256"]}` |
| Semilla | {candidato["semilla"]} |

## 2. Uso previsto

- **Para qué sirve:** estimar, con los datos de hoy de una estación, la probabilidad de que mañana
  el promedio diario de PM2.5 supere {_n(config.UMBRAL_PM25, 0)} µg/m³, como ayuda para avisar
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
| Entrenamiento | {config.TRAIN_INICIO} a {config.TRAIN_FIN} |
| Validación | {config.VAL_INICIO} a {config.VAL_FIN} |
| Producción simulada | {config.PRODUCCION_INICIO} a {config.PRODUCCION_FIN} |

- El modelo se ajusta solo con entrenamiento. La imputación y el escalado también.
- Variables de entrada: 13 numéricas (contaminantes, meteorología y PM2.5 de ayer y antier) y 3
  categóricas (dirección del viento, estación y estación del año).

## 5. Rendimiento

La métrica principal es la **sensibilidad**: no avisar un día malo es el error más costoso. La
línea base es "mañana = hoy".

| Partición | Modelo | Sensibilidad | Precisión | F1 |
|---|---|---|---|---|
{filas}

Hiperparámetros: {p["n_estimators"]} árboles, tasa de aprendizaje {_n(p["learning_rate"], 2)},
{p["num_leaves"]} hojas, `class_weight="{p["class_weight"]}"`, umbral de decisión
{_n(p["umbral_decision"], 1)}.

### Por estación (validación 2015, de menor a mayor sensibilidad)

{_tabla_estaciones(candidato["metricas"]["por_estacion_validacion"])}

Cada estación tiene unos 360 días evaluados, así que cada cifra tiene un margen de error
aproximado de ±8 puntos. Las estaciones con menor sensibilidad, al inicio de la tabla, son las
que pueden no mejorar a la línea base; ver limitaciones.

## 6. Cómo se aprobó

Antes de servir el modelo pasó por la compuerta de promoción (`make promote`):

{comprobaciones}

Precisión mínima exigida: {_n(config.PRECISION_MINIMA, 2)} (valor inicial, pendiente de confirmar
por el equipo). {historial_txt} Detalle de la política en
[`politica-de-reentrenamiento.md`](politica-de-reentrenamiento.md) y de la decisión en el
[ADR 004](adr/004-mlflow-local-y-compuerta.md).

## 7. Limitaciones y riesgos

- **No mejora en todas las estaciones.** En Huairou la sensibilidad queda por debajo de la línea
  base y en Changping empata. La causa no se ha investigado.
- **Pierde rendimiento con el tiempo.** La sensibilidad baja de validación a producción
  ({_n(mc["val"]["sensibilidad"], 2)} a {_n(mc["produccion"]["sensibilidad"], 2)}) y el reporte de
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
rollback se hace moviendo el alias `{config.ALIAS_VIGENTE}` a una versión anterior
(`--volver-a VERSION`).
"""


def generar(
    ruta_candidato: Path | None = None,
    ruta_promociones: Path | None = None,
    destino: Path | None = None,
) -> Path:
    candidato = _leer(ruta_candidato or config.REPORTES / "candidato.json")
    historial = _leer(ruta_promociones or config.REPORTE_PROMOCIONES)
    destino = destino or DESTINO
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(construir(candidato, historial), encoding="utf-8", newline="\n")
    return destino


def main() -> None:
    print(f"Ficha del modelo escrita en {generar()}")


if __name__ == "__main__":
    main()
