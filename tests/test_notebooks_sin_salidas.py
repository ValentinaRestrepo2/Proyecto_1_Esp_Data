"""Los notebooks deben guardarse sin salidas ni contadores de ejecución.

El profesor penaliza notebooks con outputs; además evita diffs enormes en Git.
Para limpiar uno: en VS Code, "Clear All Outputs" y guardar.
"""

import json
from pathlib import Path

import pytest

NOTEBOOKS = sorted(Path("notebooks").glob("*.ipynb"))


@pytest.mark.parametrize("ruta", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook_sin_salidas(ruta):
    celdas = json.loads(ruta.read_text(encoding="utf-8"))["cells"]
    con_salida = [
        i
        for i, c in enumerate(celdas)
        if c["cell_type"] == "code" and (c.get("outputs") or c.get("execution_count"))
    ]
    assert not con_salida, f"{ruta.name}: celdas con salidas guardadas: {con_salida}"


def test_hay_al_menos_un_notebook():
    assert NOTEBOOKS, "No se encontraron notebooks en notebooks/"
