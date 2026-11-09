"""Pipeline de calidad del aire con Prefect.

    descargar -> cargar -> validar crudo -> preparar -> validar procesado
                                              |-> drift -> guardar reporte
                                              |-> dividir -> entrenar -> evaluar -> registrar

El grafo sale de las dependencias de datos: cada tarea recibe el resultado de la anterior.

Decisiones de diseño:
- **Reintentos solo donde hay I/O de red** (la descarga), con backoff exponencial y
  únicamente ante errores de red. Ver `config.DESCARGA_REINTENTOS`.
- **Caché medido** en las dos tareas costosas (preparar y drift). La llave incluye la
  huella de los datos, los umbrales y el código del módulo: si cambia cualquiera de
  los tres, se recalcula. `--medir-cache` reporta el efecto real.
- **El flujo NO promueve nada.** Entrena un candidato, lo evalúa y lo registra con
  `promovido: False`. Promover es decisión de una persona (ver
  `docs/politica-de-reentrenamiento.md`).

Uso:
    uv run python -m proyecto_1_esp_data.pipeline.flow                # una ejecución
    uv run python -m proyecto_1_esp_data.pipeline.flow --medir-cache  # 2 ejecuciones cronometradas
    uv run python -m proyecto_1_esp_data.pipeline.flow --servir       # con schedule trimestral
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from proyecto_1_esp_data import config

# Se fijan ANTES de importar Prefect, que lee su configuración al importarse:
# - sin telemetría (evita escrituras extra en su base SQLite local);
# - los resultados cacheados viven dentro del proyecto (carpeta ignorada por Git).
os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED", "false")
os.environ.setdefault("PREFECT_LOCAL_STORAGE_PATH", str(config.CACHE_PREFECT.resolve()))

import pandas as pd
import requests
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact, create_table_artifact
from prefect.schedules import Cron
from prefect.tasks import exponential_backoff

from proyecto_1_esp_data.data import contract, download, prepare
from proyecto_1_esp_data.monitoring import drift
from proyecto_1_esp_data.pipeline.entrenadores import ENTRENADORES, Candidato

NOMBRE_DEPLOYMENT = "calidad-aire-trimestral"
NOMBRE_CANDIDATO = "candidato.json"


# --- Caché -------------------------------------------------------------------------


def huella_datos(ruta: str | Path) -> str:
    """SHA-256 del CSV: identifica la versión exacta de los datos."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _llave(*partes: object) -> str:
    # PIPELINE_CACHE_SALT permite forzar un fallo de caché controlado (ver --medir-cache)
    sal = os.environ.get("PIPELINE_CACHE_SALT", "")
    return hashlib.sha256("|".join(map(str, (sal, *partes))).encode()).hexdigest()


def _codigo(*modulos) -> str:
    """Huella del código fuente: si cambia la lógica, el caché se invalida."""
    return hashlib.sha256(
        "".join(inspect.getsource(m) for m in modulos).encode()
    ).hexdigest()


def llave_preparar(contexto, parametros) -> str:
    return _llave(
        "preparar",
        parametros["huella"],
        config.UMBRAL_PM25,
        config.HORAS_VALIDAS_MIN_POR_DIA,
        config.RELLENO_MAX_HORAS,
        _codigo(prepare),
    )


def llave_drift(contexto, parametros) -> str:
    return _llave(
        "drift",
        parametros["huella"],
        config.DRIFT_REFERENCIA,
        config.DRIFT_ACTUAL,
        config.DRIFT_UMBRAL_COLUMNA,
        config.DRIFT_UMBRAL_COMPARTIDO,
        config.DRIFT_COLUMNAS_NUM,
        config.DRIFT_COLUMNAS_CAT,
        _codigo(prepare, drift),
    )


# --- Tareas ------------------------------------------------------------------------


def _solo_errores_de_red(tarea, corrida, estado) -> bool:
    """Reintentar solo si la causa es de red; un hash distinto no se arregla reintentando."""
    excepcion = estado.result(raise_on_failure=False)
    return isinstance(excepcion, requests.RequestException)


@task(
    retries=config.DESCARGA_REINTENTOS,
    retry_delay_seconds=exponential_backoff(
        backoff_factor=config.DESCARGA_BACKOFF_SEGUNDOS
    ),
    retry_jitter_factor=0.5,
    retry_condition_fn=_solo_errores_de_red,
)
def asegurar_datos(ruta_csv: str, descargar_si_falta: bool) -> str:
    """Devuelve la ruta del CSV; si no existe, lo descarga de UCI."""
    log = get_run_logger()
    ruta = Path(ruta_csv)
    if ruta.exists():
        log.info("Datos ya presentes: %s", ruta)
        return str(ruta)
    if not descargar_si_falta:
        raise FileNotFoundError(f"Falta {ruta}: corre `make data`")
    if ruta.name != download.ARCHIVO_CSV:
        raise ValueError(f"Se esperaba un archivo llamado {download.ARCHIVO_CSV}")
    log.info("Descargando datos de UCI...")
    return str(download.descargar(ruta.parent))


@task
def cargar_crudo(ruta_csv: str) -> pd.DataFrame:
    df = prepare.cargar_crudo(ruta_csv)
    get_run_logger().info("Datos crudos: %s filas, %s columnas", *df.shape)
    return df


@task
def validar_crudo(crudo: pd.DataFrame, volumen: bool) -> None:
    """Contrato del dato crudo. Si falla, el flujo se detiene aquí."""
    contract.validar_o_fallar(crudo, volumen=volumen)
    get_run_logger().info("Contrato crudo: OK")


@task(
    cache_key_fn=llave_preparar,
    persist_result=True,
)
def preparar_tabla(crudo: pd.DataFrame, huella: str) -> pd.DataFrame:
    """Tabla diaria con target y features (cacheada por versión de datos y código)."""
    tabla = prepare.construir_tabla_modelo(crudo)
    get_run_logger().info("Tabla diaria: %s filas", len(tabla))
    return tabla


@task
def validar_procesado(tabla: pd.DataFrame) -> None:
    """Contrato de la tabla procesada: calendario, target y rezagos sin fuga."""
    contract.validar_procesado_o_fallar(tabla)
    get_run_logger().info("Contrato procesado: OK")


@task(cache_key_fn=llave_drift, persist_result=True)
def calcular_drift(tabla: pd.DataFrame, huella: str) -> dict:
    """Drift entre las ventanas de `config.py` (cacheado: es la tarea más lenta)."""
    resultado, resumen = drift.evaluar(tabla)
    return {"resumen": resumen, "html": resultado.get_html_str(as_iframe=False)}


@task
def guardar_reporte_drift(drift_calculado: dict, salida: str) -> dict:
    """Escribe el HTML y el JSON, y publica el resumen como artifact de la corrida."""
    resumen = drift_calculado["resumen"]
    carpeta = Path(salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / drift.NOMBRE_HTML).write_text(drift_calculado["html"], encoding="utf-8")
    (carpeta / drift.NOMBRE_RESUMEN).write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    create_markdown_artifact(
        key="drift",
        description="Drift entre la ventana de referencia y la actual",
        markdown=(
            f"## Drift detectado: **{resumen['drift_detectado']}**\n\n"
            f"- Columnas con drift: {len(resumen['columnas_con_drift'])} de "
            f"{resumen['columnas_evaluadas']} ({resumen['proporcion_con_drift']:.0%})\n"
            f"- Columnas: {', '.join(resumen['columnas_con_drift']) or 'ninguna'}\n"
            f"- Referencia: {resumen['referencia']['inicio']} a {resumen['referencia']['fin']}\n"
            f"- Actual: {resumen['actual']['inicio']} a {resumen['actual']['fin']}\n"
            f"- Reporte completo: `{carpeta / drift.NOMBRE_HTML}`\n\n"
            f"{resumen['accion']}"
        ),
    )
    return resumen


@task
def dividir_tabla(tabla: pd.DataFrame) -> dict[str, pd.DataFrame]:
    partes = prepare.dividir(tabla)
    get_run_logger().info("Particiones: %s", {k: len(v) for k, v in partes.items()})
    return partes


@task
def entrenar_candidato(partes: dict[str, pd.DataFrame], modelo: str) -> Candidato:
    if modelo not in ENTRENADORES:
        raise ValueError(
            f"Modelo desconocido: {modelo}. Disponibles: {sorted(ENTRENADORES)}"
        )
    candidato = ENTRENADORES[modelo](partes)
    get_run_logger().info("Candidato entrenado: %s", candidato.nombre)
    return candidato


@task
def evaluar(candidato: Candidato, partes: dict[str, pd.DataFrame]) -> dict:
    """Métricas del candidato y de la línea base en validación y producción simulada."""
    metricas = {"candidato": candidato.nombre, "modelo": {}, "linea_base": {}}
    for nombre in ("val", "produccion"):
        parte = partes[nombre]
        metricas["modelo"][nombre] = prepare.metricas(
            parte["target"], candidato.predecir(parte)
        )
        metricas["linea_base"][nombre] = prepare.metricas(
            parte["target"], prepare.baseline_persistencia(parte)
        )
    por_estacion = prepare.metricas_por_estacion(
        partes["val"], candidato.predecir(partes["val"])
    )
    metricas["por_estacion_validacion"] = por_estacion.round(3).to_dict(orient="index")

    filas = [
        {"particion": p, "modelo": cual, **{k: round(v, 3) for k, v in m.items()}}
        for cual in ("modelo", "linea_base")
        for p, m in metricas[cual].items()
    ]
    create_table_artifact(
        key="metricas",
        table=filas,
        description="Sensibilidad (principal), precisión y F1 del candidato y de la línea base",
    )
    return metricas


@task
def registrar_candidato(
    candidato: Candidato, metricas: dict, huella: str, salida: str
) -> dict:
    """Registra el candidato. NO lo promueve: eso es decisión de una persona."""
    registro = {
        "candidato": candidato.nombre,
        "parametros": candidato.parametros,
        "semilla": config.SEMILLA,
        "huella_datos_sha256": huella,
        "metricas": metricas,
        "promovido": False,
        "nota": "El pipeline no promueve modelos; ver docs/politica-de-reentrenamiento.md",
    }
    carpeta = Path(salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / NOMBRE_CANDIDATO).write_text(
        json.dumps(registro, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    get_run_logger().info(
        "Candidato registrado (promovido=False): %s", carpeta / NOMBRE_CANDIDATO
    )
    return registro


# --- Flujo -------------------------------------------------------------------------


@flow(name="calidad-aire", log_prints=True)
def flujo_calidad_aire(
    modelo: str = "baseline",
    ruta_csv: str = str(config.CSV_CRUDO),
    salida: str = str(config.REPORTES),
    validar_volumen: bool = True,
    descargar_si_falta: bool = True,
) -> dict:
    """Corre el pipeline completo de punta a punta con un solo comando."""
    inicio = time.perf_counter()
    ruta = asegurar_datos(ruta_csv, descargar_si_falta)
    crudo = cargar_crudo(ruta)
    validar_crudo(crudo, validar_volumen)

    huella = huella_datos(ruta)
    tabla = preparar_tabla(crudo, huella, wait_for=[validar_crudo])
    validar_procesado(tabla)

    resumen_drift = guardar_reporte_drift(calcular_drift(tabla, huella), salida)

    partes = dividir_tabla(tabla, wait_for=[validar_procesado])
    candidato = entrenar_candidato(partes, modelo)
    metricas = evaluar(candidato, partes)
    registro = registrar_candidato(candidato, metricas, huella, salida)
    return {
        "drift": resumen_drift,
        "registro": registro,
        # Tiempo del flujo mismo, sin el arranque del servidor temporal de Prefect
        "duracion_s": round(time.perf_counter() - inicio, 3),
    }


# --- Línea de comandos -------------------------------------------------------------


def medir_cache(**parametros) -> dict:
    """Corre el flujo dos veces seguidas y compara los tiempos (primera sin caché)."""
    os.environ["PIPELINE_CACHE_SALT"] = (
        uuid.uuid4().hex
    )  # garantiza fallo de caché inicial
    shutil.rmtree(config.CACHE_PREFECT, ignore_errors=True)
    tiempos = [flujo_calidad_aire(**parametros)["duracion_s"] for _ in range(2)]
    resultado = {
        "primera_ejecucion_s": round(tiempos[0], 2),
        "segunda_ejecucion_s": round(tiempos[1], 2),
        "aceleracion": round(tiempos[0] / tiempos[1], 2),
    }
    print(f"Caché medido: {json.dumps(resultado)}")
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pipeline de calidad del aire (Prefect)"
    )
    parser.add_argument("--modelo", default="baseline", choices=sorted(ENTRENADORES))
    parser.add_argument(
        "--medir-cache", action="store_true", help="2 ejecuciones cronometradas"
    )
    parser.add_argument(
        "--servir", action="store_true", help="queda corriendo con el schedule"
    )
    args = parser.parse_args(argv)

    if args.servir:
        flujo_calidad_aire.serve(
            name=NOMBRE_DEPLOYMENT,
            schedule=Cron(config.PIPELINE_CRON, timezone=config.PIPELINE_ZONA_HORARIA),
            parameters={"modelo": args.modelo},
        )
    elif args.medir_cache:
        medir_cache(modelo=args.modelo)
    else:
        flujo_calidad_aire(modelo=args.modelo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
