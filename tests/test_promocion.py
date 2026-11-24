"""Compuerta de promoción: las reglas son una función pura y la decisión queda escrita."""

import json
from pathlib import Path

import pytest

from proyecto_1_esp_data import config, promocion, registro, train
from proyecto_1_esp_data.data import prepare

MUESTRA = Path(__file__).parent / "fixtures" / "muestra_beijing.csv"


def metricas(sens_val, sens_prod=None, precision_val=0.7):
    return {
        "val": {"sensibilidad": sens_val, "precision": precision_val, "f1": 0.7},
        "produccion": {
            "sensibilidad": sens_val if sens_prod is None else sens_prod,
            "precision": 0.7,
            "f1": 0.7,
        },
    }


BASE = metricas(0.64, 0.59, precision_val=0.64)


# --- Reglas (función pura) -------------------------------------------------------------


def test_candidato_que_supera_la_linea_base_se_aprueba_si_no_hay_vigente():
    decision = promocion.decidir(metricas(0.74, 0.65), BASE, vigente=None)
    assert decision.aprobado
    assert decision.razones_de_rechazo == []


def test_candidato_peor_que_la_linea_base_se_rechaza():
    decision = promocion.decidir(metricas(0.60, 0.65), BASE, vigente=None)
    assert not decision.aprobado
    assert any("val supera a la línea base" in r for r in decision.razones_de_rechazo)


def test_candidato_que_no_supera_la_linea_base_en_produccion_se_rechaza():
    decision = promocion.decidir(metricas(0.74, 0.55), BASE, vigente=None)
    assert not decision.aprobado
    assert any("produccion" in r for r in decision.razones_de_rechazo)


def test_precision_bajo_el_minimo_se_rechaza_aunque_la_sensibilidad_sea_alta():
    candidato = metricas(0.95, 0.90, precision_val=0.45)  # avisa casi todos los días
    decision = promocion.decidir(candidato, BASE, vigente=None, precision_minima=0.60)
    assert not decision.aprobado
    assert any("Precisión" in r for r in decision.razones_de_rechazo)


def test_candidato_igual_al_vigente_se_rechaza():
    vigente = metricas(0.74, 0.65)
    decision = promocion.decidir(metricas(0.74, 0.65), BASE, vigente)
    assert not decision.aprobado
    assert any("vigente" in r for r in decision.razones_de_rechazo)


def test_candidato_mejor_que_el_vigente_se_aprueba():
    decision = promocion.decidir(metricas(0.78, 0.66), BASE, metricas(0.74, 0.65))
    assert decision.aprobado


def test_la_decision_lista_todas_las_reglas_evaluadas():
    decision = promocion.decidir(metricas(0.74, 0.65), BASE, metricas(0.70, 0.60))
    assert len(decision.comprobaciones) == 4  # 2 contra la base, precisión, vigente
    assert all(
        {"regla", "cumple", "detalle"} <= set(c) for c in decision.comprobaciones
    )


# --- Con MLflow (registro temporal) ----------------------------------------------------


@pytest.fixture(scope="session")
def plantilla_dos_candidatos(base_mlflow_migrada, copiar_base, tmp_path_factory):
    """Entrena dos candidatos UNA vez por sesión (es lo más caro de estas pruebas).

    Devuelve (base de datos, versiones). Cada prueba trabaja sobre una copia de la base;
    los artefactos del modelo se quedan aquí y solo se leen, porque las pruebas de la
    compuerta cambian alias y etiquetas (que viven en la base), no los artefactos.
    """
    carpeta = tmp_path_factory.mktemp("dos_candidatos")
    base = carpeta / "mlflow.db"
    copiar_base(base_mlflow_migrada, base)
    tabla = prepare.construir_tabla_modelo(prepare.cargar_crudo(MUESTRA))
    partes = {
        "train": tabla.iloc[:10],
        "val": tabla.iloc[10:15],
        "produccion": tabla.iloc[15:],
    }
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(carpeta)
        mp.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{base.as_posix()}")
        versiones = [
            train.entrenar_y_registrar(partes, f"h{i}", verbose=False)["version"]
            for i in (1, 2)
        ]
    return base, versiones


@pytest.fixture
def dos_candidatos(plantilla_dos_candidatos, copiar_base, tmp_path, monkeypatch):
    """Dos candidatos registrados y las métricas que ve la compuerta, controladas.

    Con 20 filas las métricas reales no dicen nada, así que se fijan: la versión 1 es
    buena y la 2 es idéntica. Lo que se prueba es el registro, los alias y el historial.
    """
    base, versiones = plantilla_dos_candidatos
    destino = tmp_path / "mlflow.db"
    copiar_base(base, destino)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{destino.as_posix()}")
    fijas = {
        "modelo": metricas(0.74, 0.65, precision_val=0.68),
        "linea_base": BASE,
    }
    monkeypatch.setattr(registro, "metricas_de_version", lambda client, v: fijas)
    return versiones, tmp_path / "promociones.json"


def test_se_promueve_el_primero_y_se_rechaza_el_segundo(dos_candidatos):
    (v1, v2), reporte = dos_candidatos
    client = registro.cliente()

    # El alias `candidate` apunta a la versión 2; se evalúa la 1 de forma explícita.
    primera = promocion.promover("Santiago", version=v1, ruta_reporte=reporte)
    assert primera["decision"] == "aprobado"
    vigente = registro.version_por_alias(client, config.ALIAS_VIGENTE)
    assert str(vigente.version) == v1
    assert vigente.tags["validation_status"] == "aprobado"
    assert vigente.tags["decidido_por"] == "Santiago"

    # La versión 2 es igual: no supera al vigente, así que se rechaza y no lo desplaza
    segunda = promocion.promover("Santiago", ruta_reporte=reporte)
    assert segunda["decision"] == "rechazado"
    assert segunda["version_anterior"] == v1
    assert any("vigente" in r for r in segunda["razones_de_rechazo"])
    assert str(registro.version_por_alias(client, config.ALIAS_VIGENTE).version) == v1
    rechazada = client.get_model_version(config.MODELO_REGISTRADO, v2)
    assert rechazada.tags["validation_status"] == "rechazado"
    assert "vigente" in rechazada.tags["razones_de_rechazo"]


def test_el_historial_guarda_cada_decision_con_su_evidencia(dos_candidatos):
    (v1, _), reporte = dos_candidatos
    promocion.promover("Santiago", version=v1, ruta_reporte=reporte)
    promocion.promover("Valentina", ruta_reporte=reporte)

    historial = json.loads(reporte.read_text(encoding="utf-8"))
    assert [h["decision"] for h in historial] == ["aprobado", "rechazado"]
    assert [h["decidido_por"] for h in historial] == ["Santiago", "Valentina"]
    assert historial[1]["comprobaciones"] and historial[1]["metricas_vigente"]


def test_no_se_puede_promover_lo_que_ya_es_el_vigente(dos_candidatos):
    (v1, _), reporte = dos_candidatos
    promocion.promover("Santiago", version=v1, ruta_reporte=reporte)
    with pytest.raises(ValueError, match="ya es el modelo vigente"):
        promocion.promover("Santiago", version=v1, ruta_reporte=reporte)


def test_rollback_devuelve_el_vigente_a_una_version_anterior(dos_candidatos):
    (v1, v2), reporte = dos_candidatos
    promocion.promover("Santiago", version=v1, ruta_reporte=reporte)
    client = registro.cliente()
    # Se fuerza la 2 como vigente para simular un modelo nuevo que salió mal
    client.set_registered_model_alias(
        config.MODELO_REGISTRADO, config.ALIAS_VIGENTE, v2
    )

    entrada = promocion.volver_a(v1, "Santiago", ruta_reporte=reporte)

    assert entrada["accion"] == "rollback"
    assert entrada["version_anterior"] == v2
    assert str(registro.version_por_alias(client, config.ALIAS_VIGENTE).version) == v1


def test_sin_candidato_pide_entrenar_primero(registro_aislado):
    tmp_path = registro_aislado
    with pytest.raises(LookupError, match="make train"):
        promocion.promover("Santiago", ruta_reporte=tmp_path / "p.json")


def test_main_sale_con_codigo_1_si_rechaza(dos_candidatos, monkeypatch):
    (v1, _), reporte = dos_candidatos
    monkeypatch.setattr(config, "REPORTE_PROMOCIONES", reporte)
    assert promocion.main(["--aprobador", "Santiago", "--version", v1]) == 0
    assert promocion.main(["--aprobador", "Santiago"]) == 1
