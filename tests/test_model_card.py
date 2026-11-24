"""La ficha del modelo se genera desde los reportes y no inventa cifras."""

from __future__ import annotations

import json

import pytest

from proyecto_1_esp_data import config, model_card

METRICAS = {
    "val": {"sensibilidad": 0.8, "precision": 0.7, "f1": 0.75},
    "produccion": {"sensibilidad": 0.7, "precision": 0.65, "f1": 0.67},
}
BASE = {
    "val": {"sensibilidad": 0.6, "precision": 0.6, "f1": 0.6},
    "produccion": {"sensibilidad": 0.55, "precision": 0.55, "f1": 0.55},
}


def _decision(version: str, decision: str, quien: str) -> dict:
    return {
        "fecha_utc": "2026-11-24T05:15:16+00:00",
        "accion": "promocion",
        "version": version,
        "decision": decision,
        "decidido_por": quien,
        "comprobaciones": [
            {"regla": "Regla de prueba", "cumple": True, "detalle": "ok"}
        ],
        "metricas_candidato": METRICAS,
        "metricas_linea_base": BASE,
        "huella_datos_sha256": "abc123",
    }


@pytest.fixture
def reportes(tmp_path):
    candidato = {
        "semilla": 42,
        "parametros": {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "class_weight": "balanced",
            "umbral_decision": 0.5,
        },
        "metricas": {
            "por_estacion_validacion": {
                "Bien": {"n": 360.0, "sensibilidad": 0.9, "precision": 0.8, "f1": 0.8},
                "Mal": {"n": 360.0, "sensibilidad": 0.5, "precision": 0.8, "f1": 0.6},
            }
        },
    }
    historial = [_decision("1", "aprobado", "Ana"), _decision("2", "rechazado", "Luis")]
    ruta_c = tmp_path / "candidato.json"
    ruta_h = tmp_path / "promociones.json"
    ruta_c.write_text(json.dumps(candidato), encoding="utf-8")
    ruta_h.write_text(json.dumps(historial), encoding="utf-8")
    return ruta_c, ruta_h


def test_la_ficha_usa_la_version_aprobada_y_las_cifras_de_los_reportes(
    reportes, tmp_path
):
    ruta_c, ruta_h = reportes
    destino = model_card.generar(ruta_c, ruta_h, tmp_path / "salida" / "model-card.md")
    texto = destino.read_text(encoding="utf-8")
    assert "| Versión vigente | 1 |" in texto
    assert "Ana" in texto
    assert "0,800" in texto  # sensibilidad en validación, con coma decimal
    assert "1 de ellas rechazos" in texto
    assert f"`{config.MODELO_REGISTRADO}`" in texto


def test_las_estaciones_salen_de_menor_a_mayor_sensibilidad(reportes, tmp_path):
    ruta_c, ruta_h = reportes
    texto = model_card.generar(ruta_c, ruta_h, tmp_path / "m.md").read_text(
        encoding="utf-8"
    )
    assert texto.index("| Mal |") < texto.index("| Bien |")


def test_sin_promocion_aprobada_falla_con_mensaje_claro(reportes, tmp_path):
    ruta_c, ruta_h = reportes
    ruta_h.write_text(
        json.dumps([_decision("1", "rechazado", "Ana")]), encoding="utf-8"
    )
    with pytest.raises(LookupError, match="make promote"):
        model_card.generar(ruta_c, ruta_h, tmp_path / "m.md")


def test_sin_reportes_falla_con_mensaje_claro(tmp_path):
    with pytest.raises(FileNotFoundError, match="Falta"):
        model_card.generar(
            tmp_path / "no.json", tmp_path / "no2.json", tmp_path / "m.md"
        )
