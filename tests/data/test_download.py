import io
import json
import zipfile
from pathlib import Path

import pytest

from proyecto_1_esp_data.data.download import (
    construir_dataframe,
    descargar,
    verificar_hash,
)

CABECERA = "No,year,month,day,hour,PM2.5,PM10,SO2,NO2,CO,O3,TEMP,PRES,DEWP,RAIN,wd,WSPM,station"


def _csv(estacion: str) -> bytes:
    fila = f"1,2013,3,1,0,3,6,13,7,300,85,-2.3,1020.8,-19.7,0,E,0.5,{estacion}"
    return f"{CABECERA}\n{fila}\n".encode()


def _zip_anidado(n_estaciones: int = 12) -> bytes:
    interno = io.BytesIO()
    with zipfile.ZipFile(interno, "w") as z:
        for i in range(n_estaciones):
            z.writestr(f"PRSA_Data_E{i}_20130301-20170228.csv", _csv(f"E{i}"))
    externo = io.BytesIO()
    with zipfile.ZipFile(externo, "w") as z:
        z.writestr("PRSA2017_Data_20130301-20170228.zip", interno.getvalue())
    return externo.getvalue()


def test_une_zip_anidado_y_conserva_decimales():
    df = construir_dataframe(_zip_anidado(), estaciones=12, filas=12)
    assert len(df) == 12
    assert df["TEMP"].iloc[0] == -2.3  # el punto decimal no se pierde
    assert df["PRES"].iloc[0] == 1020.8


def test_rechaza_numero_incorrecto_de_estaciones():
    with pytest.raises(ValueError, match="CSV de estación"):
        construir_dataframe(_zip_anidado(11), estaciones=12, filas=11)


def test_rechaza_numero_incorrecto_de_filas():
    with pytest.raises(ValueError, match="filas"):
        construir_dataframe(_zip_anidado(), estaciones=12, filas=999)


def test_hash_distinto_es_rechazado(tmp_path: Path):
    ruta = tmp_path / "metadata.json"
    ruta.write_text(json.dumps({"sha256_zip": "abc"}), encoding="utf-8")
    with pytest.raises(ValueError, match="cambió"):
        verificar_hash("otro_hash", ruta)


def test_descargar_desde_zip_local_escribe_csv_y_metadata(tmp_path: Path, monkeypatch):
    zip_local = tmp_path / "datos.zip"
    zip_local.write_bytes(_zip_anidado())
    monkeypatch.setattr("proyecto_1_esp_data.data.download.FILAS_ESPERADAS", 12)
    ruta = descargar(destino=tmp_path / "raw", zip_local=zip_local)
    assert ruta.exists()
    meta = json.loads((tmp_path / "raw" / "metadata.json").read_text(encoding="utf-8"))
    assert meta["filas"] == 12
    assert len(meta["sha256_zip"]) == 64
