"""Los catálogos de config.py (estaciones y estaciones del año) son únicos y coherentes."""

import json
from pathlib import Path

from proyecto_1_esp_data import config
from proyecto_1_esp_data.data import prepare

RAIZ = Path(__file__).resolve().parents[2]


def test_estaciones_coinciden_con_metadata_de_los_datos():
    metadata = json.loads((RAIZ / config.METADATA).read_text(encoding="utf-8"))
    assert sorted(config.ESTACIONES) == sorted(metadata["estaciones"])


def test_volumen_esperado_sale_de_las_estaciones():
    assert config.ESTACIONES_ESPERADAS == len(config.ESTACIONES)
    assert config.FILAS_ESPERADAS == len(config.ESTACIONES) * config.FILAS_POR_ESTACION


def test_estaciones_del_ano_salen_del_mapa_por_mes():
    assert set(config.ESTACION_DEL_ANO) == set(range(1, 13))
    assert config.ESTACIONES_DEL_ANO == ["invierno", "primavera", "verano", "otono"]
    assert not hasattr(prepare, "ESTACION_DEL_ANO")
