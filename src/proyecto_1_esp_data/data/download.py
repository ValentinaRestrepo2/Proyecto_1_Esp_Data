"""Descarga y arma el dataset de calidad del aire de Beijing (UCI 501).

Por qué existe este módulo: el dataset original viene como un ZIP que contiene
otro ZIP con 12 CSV (uno por estación). Unirlos a mano con Excel o Power Query
en configuración regional en español destruye los decimales (el punto se lee
como separador de miles). Aquí se unen con pandas, sin tocar los valores.

Uso:
    uv run python -m proyecto_1_esp_data.data.download
    uv run python -m proyecto_1_esp_data.data.download --zip ruta/al/archivo.zip
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import requests

URL = "https://archive.ics.uci.edu/static/public/501/beijing+multi+site+air+quality+data.zip"
FICHA = "https://archive.ics.uci.edu/dataset/501"
LICENCIA = "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/legalcode)"
ESTACIONES_ESPERADAS = 12
FILAS_ESPERADAS = 420_768  # 12 estaciones x 35.064 horas
ARCHIVO_CSV = "calidad_aire_beijing.csv"
ARCHIVO_METADATA = "metadata.json"


def sha256(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _extraer_csvs(contenido_zip: bytes) -> list[tuple[str, bytes]]:
    """Recorre ZIPs anidados y devuelve (nombre, bytes) de cada CSV de estación."""
    salida: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(contenido_zip)) as z:
        for nombre in z.namelist():
            base = nombre.rsplit("/", 1)[-1]
            if nombre.startswith("__MACOSX") or base.startswith("._"):
                continue  # basura que añade macOS al comprimir
            datos = z.read(nombre)
            if nombre.lower().endswith(".zip"):
                salida.extend(_extraer_csvs(datos))
            elif nombre.lower().endswith(".csv") and "PRSA_Data" in base:
                salida.append((base, datos))
    return salida


def construir_dataframe(
    contenido_zip: bytes,
    estaciones: int | None = None,
    filas: int | None = None,
) -> pd.DataFrame:
    """Une los CSV de todas las estaciones sin alterar los valores."""
    estaciones = ESTACIONES_ESPERADAS if estaciones is None else estaciones
    filas = FILAS_ESPERADAS if filas is None else filas
    csvs = _extraer_csvs(contenido_zip)
    if len(csvs) != estaciones:
        raise ValueError(f"Se esperaban {estaciones} CSV de estación y hay {len(csvs)}")
    partes = [pd.read_csv(io.BytesIO(datos)) for _, datos in sorted(csvs)]
    df = pd.concat(partes, ignore_index=True)
    if len(df) != filas:
        raise ValueError(f"Se esperaban {filas} filas y hay {len(df)}")
    return df


def verificar_hash(hash_zip: str, ruta_metadata: Path) -> None:
    """Si ya hay un metadata.json, el ZIP nuevo debe tener el mismo hash."""
    if not ruta_metadata.exists():
        return
    previo = json.loads(ruta_metadata.read_text(encoding="utf-8"))
    if previo.get("sha256_zip") != hash_zip:
        raise ValueError(
            "El ZIP cambió respecto a metadata.json: los datos de la fuente "
            "no son los mismos con los que se versionó el proyecto."
        )


def descargar(
    destino: Path = Path("data/raw"),
    zip_local: Path | None = None,
    timeout: int = 120,
) -> Path:
    """Descarga (o lee) el ZIP, arma el CSV único y escribe metadata.json."""
    if zip_local is not None:
        contenido = zip_local.read_bytes()
    else:
        respuesta = requests.get(URL, timeout=timeout)
        respuesta.raise_for_status()
        contenido = respuesta.content

    destino.mkdir(parents=True, exist_ok=True)
    hash_zip = sha256(contenido)
    verificar_hash(hash_zip, destino / ARCHIVO_METADATA)

    df = construir_dataframe(contenido)
    ruta_csv = destino / ARCHIVO_CSV
    df.to_csv(ruta_csv, index=False)

    metadata = {
        "fuente": URL,
        "ficha": FICHA,
        "licencia": LICENCIA,
        "sha256_zip": hash_zip,
        "filas": len(df),
        "columnas": list(df.columns),
        "estaciones": sorted(df["station"].unique().tolist()),
    }
    (destino / ARCHIVO_METADATA).write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return ruta_csv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--zip", type=Path, default=None, help="usar un ZIP local")
    parser.add_argument("--destino", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    ruta = descargar(destino=args.destino, zip_local=args.zip)
    print(f"Listo: {ruta}")


if __name__ == "__main__":
    main()
