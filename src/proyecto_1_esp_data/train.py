"""Entrenamiento con split temporal: registra la corrida y deja un CANDIDATO.

Qué hace: ajusta el pipeline completo (preprocesador + LightGBM) solo con train, mide
el modelo y la línea base en validación y producción simulada, y lo registra en MLflow
con parámetros, métricas, firma y ejemplo de entrada.

Qué NO hace: no promueve. El modelo queda con el alias `candidate`; el modelo vigente
(`champion`, el que sirven la API y la app) solo lo mueve la compuerta de promoción
(`make promote`). Entrenar no puede cambiar lo que está en producción, porque que el
entrenamiento termine sin excepciones no dice nada sobre si el modelo es mejor.
"""

from __future__ import annotations

import mlflow
import pandas as pd
from mlflow.models import infer_signature

from proyecto_1_esp_data import config, registro
from proyecto_1_esp_data.data import prepare
from proyecto_1_esp_data.features import COLUMNAS_X, TARGET
from proyecto_1_esp_data.model import construir_pipeline

HIPERPARAMETROS = (
    "n_estimators",
    "learning_rate",
    "num_leaves",
    "class_weight",
    "random_state",
)


def entrenar_y_registrar(
    partes: dict[str, pd.DataFrame], huella_datos: str, verbose: bool = True
) -> dict:
    """Ajusta con `partes["train"]`, evalúa y registra la versión como candidata."""
    train = partes["train"]
    pipeline = construir_pipeline().fit(train[COLUMNAS_X], train[TARGET])

    modelo, linea_base = {}, {}
    for nombre in registro.PARTICIONES:
        parte = partes[nombre]
        proba = pipeline.predict_proba(parte[COLUMNAS_X])[:, 1]
        y_pred = pd.Series(
            (proba >= config.UMBRAL_DECISION).astype(int), index=parte.index
        )
        modelo[nombre] = prepare.metricas(parte[TARGET], y_pred)
        linea_base[nombre] = prepare.metricas(
            parte[TARGET], prepare.baseline_persistencia(parte)
        )

    client = registro.cliente()
    mlflow.set_experiment(config.MLFLOW_EXPERIMENTO)
    clasificador = pipeline.named_steps["clasificador"].get_params()

    with mlflow.start_run(run_name="lightgbm") as corrida:
        mlflow.log_params(
            {clave: clasificador[clave] for clave in HIPERPARAMETROS}
            | {
                "umbral_decision": config.UMBRAL_DECISION,
                "semilla": config.SEMILLA,
                "huella_datos_sha256": huella_datos,
                "train": f"{config.TRAIN_INICIO} a {config.TRAIN_FIN}",
                "validacion": f"{config.VAL_INICIO} a {config.VAL_FIN}",
                "produccion": f"{config.PRODUCCION_INICIO} a {config.PRODUCCION_FIN}",
                "filas_train": len(train),
            }
        )
        for nombre in registro.PARTICIONES:
            for metrica in registro.METRICAS:
                mlflow.log_metric(f"{nombre}_{metrica}", modelo[nombre][metrica])
                mlflow.log_metric(
                    f"{registro.PREFIJO_LINEA_BASE}{nombre}_{metrica}",
                    linea_base[nombre][metrica],
                )

        # El preprocesamiento va DENTRO del artefacto: un solo objeto, nada que sincronizar
        ejemplo = train[COLUMNAS_X].head(3)
        info = mlflow.sklearn.log_model(
            pipeline,
            name="modelo",
            signature=infer_signature(ejemplo, pipeline.predict(ejemplo)),
            input_example=ejemplo,
            registered_model_name=config.MODELO_REGISTRADO,
            # El formato por defecto de MLflow (skops) exige declarar cada tipo de
            # LightGBM como "confiable"; cloudpickle guarda el pipeline completo tal cual.
            # Solo se cargan modelos de nuestro propio registro, nunca de terceros.
            serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
        )
        version = str(info.registered_model_version)

    client.set_registered_model_alias(
        config.MODELO_REGISTRADO, config.ALIAS_CANDIDATO, version
    )
    client.set_model_version_tag(
        config.MODELO_REGISTRADO, version, "validation_status", "pendiente"
    )
    client.set_model_version_tag(
        config.MODELO_REGISTRADO, version, "huella_datos_sha256", huella_datos
    )

    resultado = {
        "version": version,
        "run_id": corrida.info.run_id,
        "metricas": {"modelo": modelo, "linea_base": linea_base},
    }
    if verbose:
        for nombre in registro.PARTICIONES:
            print(f"{nombre}: {modelo[nombre]}")
            print(f"{nombre} (línea base): {linea_base[nombre]}")
        print(
            f"Candidato registrado: {config.MODELO_REGISTRADO} versión {version} "
            f"(alias {config.ALIAS_CANDIDATO}). No es el modelo vigente todavía: "
            "para promoverlo corre `make promote`."
        )
    return resultado


def entrenar(verbose: bool = True, ruta_csv=config.CSV_CRUDO) -> dict:
    """Entrena con los datos reales y registra el candidato."""
    tabla = prepare.construir_tabla_modelo(prepare.cargar_crudo(ruta_csv))
    partes = prepare.dividir(tabla)
    return entrenar_y_registrar(partes, registro.huella_archivo(ruta_csv), verbose)


if __name__ == "__main__":
    entrenar()
