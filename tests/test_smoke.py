"""Pruebas del diagnóstico de entorno."""

from proyecto_1_esp_data import smoke


def test_particiones_de_config_son_coherentes():
    assert smoke._particiones() == []


def test_smoke_lista_lo_que_falta(tmp_path):
    problemas = smoke.verificar_entorno(tmp_path)  # carpeta vacía
    assert any("uv.lock" in p for p in problemas)
    assert any("calidad_aire_beijing.csv" in p for p in problemas)
    assert any("metadata.json" in p for p in problemas)


def test_smoke_detecta_datos_que_rompen_el_contrato(tmp_path):
    datos = tmp_path / "data" / "raw"
    datos.mkdir(parents=True)
    (datos / "calidad_aire_beijing.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    problemas = smoke.verificar_entorno(tmp_path)
    assert any("Contrato de datos" in p for p in problemas)


def test_smoke_main_devuelve_1_si_algo_falla(monkeypatch, capsys):
    monkeypatch.setattr(smoke, "verificar_entorno", lambda: ["falta algo"])
    assert smoke.main() == 1
    assert "falta algo" in capsys.readouterr().out


def test_smoke_main_devuelve_0_si_todo_esta_bien(monkeypatch):
    monkeypatch.setattr(smoke, "verificar_entorno", list)  # list() == []
    assert smoke.main() == 0
