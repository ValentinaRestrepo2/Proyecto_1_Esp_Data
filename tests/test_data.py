"""Carga del dataset con la muestra creada en tests/fixtures/."""

from pathlib import Path

from proyecto_1_esp_data.data import prepare

MUESTRA = Path(__file__).parent / "fixtures" / "muestra_beijing.csv"


def test_carga_muestra_con_columnas_esperadas():
    df = prepare.cargar_crudo(MUESTRA)
    for c in ["year", "month", "day", "hour", "PM2.5", "station", "wd"]:
        assert c in df.columns
    assert len(df) == 500


def test_tabla_diaria_una_fila_por_dia():
    diaria = prepare.tabla_diaria(prepare.cargar_crudo(MUESTRA))
    assert not diaria.duplicated(["station", "fecha"]).any()