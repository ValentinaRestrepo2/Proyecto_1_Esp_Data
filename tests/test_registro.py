"""Entrenar registra una corrida completa y deja un CANDIDATO, nunca el modelo vigente."""

from pathlib import Path

import mlflow
import pytest

from proyecto_1_esp_data import config, registro, train
from proyecto_1_esp_data.data import prepare

MUESTRA = Path(__file__).parent / "fixtures" / "muestra_beijing.csv"


@pytest.fixture
def registro_temporal(registro_aislado):
    """Registro vacío en una carpeta temporal (la base y los artefactos quedan ahí)."""
    return registro_aislado


@pytest.fixture
def partes():
    """La muestra de 20 días repartida en train, val y producción."""
    tabla = prepare.construir_tabla_modelo(prepare.cargar_crudo(MUESTRA))
    return {
        "train": tabla.iloc[:10],
        "val": tabla.iloc[10:15],
        "produccion": tabla.iloc[15:],
    }


def test_entrenar_deja_un_candidato_y_no_toca_el_vigente(registro_temporal, partes):
    resultado = train.entrenar_y_registrar(partes, "huella-de-prueba", verbose=False)
    client = registro.cliente()

    candidato = registro.version_por_alias(client, config.ALIAS_CANDIDATO)
    assert candidato is not None
    assert str(candidato.version) == resultado["version"]
    assert candidato.tags["validation_status"] == "pendiente"
    assert candidato.tags["huella_datos_sha256"] == "huella-de-prueba"
    # Entrenar nunca promueve: el modelo vigente sigue sin existir
    assert registro.version_por_alias(client, config.ALIAS_VIGENTE) is None


def test_la_corrida_guarda_parametros_metricas_y_firma(registro_temporal, partes):
    resultado = train.entrenar_y_registrar(partes, "h", verbose=False)
    corrida = registro.cliente().get_run(resultado["run_id"])

    assert corrida.data.params["semilla"] == str(config.SEMILLA)
    assert corrida.data.params["huella_datos_sha256"] == "h"
    # Métricas del modelo y de la línea base, en las dos particiones
    esperadas = registro.nombres_de_metricas() + registro.nombres_de_metricas(
        registro.PREFIJO_LINEA_BASE
    )
    assert set(esperadas) <= set(corrida.data.metrics)

    uri = f"models:/{config.MODELO_REGISTRADO}@{config.ALIAS_CANDIDATO}"
    info = mlflow.models.get_model_info(uri)
    assert info.signature is not None  # firma presente
    assert info.saved_input_example_info is not None  # ejemplo de entrada presente


def test_el_modelo_registrado_incluye_el_preprocesamiento(registro_temporal, partes):
    """Un solo artefacto: carga y predice sobre columnas crudas, sin archivos aparte."""
    train.entrenar_y_registrar(partes, "h", verbose=False)
    modelo = mlflow.sklearn.load_model(
        f"models:/{config.MODELO_REGISTRADO}@{config.ALIAS_CANDIDATO}"
    )
    assert "preprocesador" in modelo.named_steps
    assert modelo.predict_proba(partes["val"][modelo.feature_names_in_]).shape[1] == 2
