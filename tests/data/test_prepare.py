"""Pruebas de la tabla diaria, el target, el split temporal y la línea base."""

import numpy as np
import pandas as pd
import pytest

from proyecto_1_esp_data import config
from proyecto_1_esp_data.data import prepare


def _horas(fecha: str, pm25, estacion: str = "A") -> pd.DataFrame:
    """24 filas horarias de un día. `pm25` es un valor o una lista de 24 valores."""
    f = pd.Timestamp(fecha)
    valores = [pm25] * 24 if np.isscalar(pm25) else list(pm25)
    return pd.DataFrame(
        {
            "year": f.year,
            "month": f.month,
            "day": f.day,
            "hour": range(24),
            "PM2.5": valores,
            "PM10": 100.0,
            "SO2": 5.0,
            "NO2": 30.0,
            "CO": 500.0,
            "O3": 40.0,
            "TEMP": 10.0,
            "PRES": 1010.0,
            "DEWP": 0.0,
            "RAIN": 0.0,
            "WSPM": 1.0,
            "wd": "N",
            "station": estacion,
        }
    )


def _crudo(dias: dict[str, float | list], estacion: str = "A") -> pd.DataFrame:
    return pd.concat(
        [_horas(f, v, estacion) for f, v in dias.items()], ignore_index=True
    )


def test_dia_con_pocas_horas_validas_no_se_usa():
    pocas = [50.0] * 10 + [np.nan] * 14  # solo 10 horas válidas y huecos largos
    diaria = prepare.tabla_diaria(_crudo({"2014-01-01": pocas}))
    assert np.isnan(diaria.loc[0, "pm25"])


def test_dia_con_horas_suficientes_se_usa():
    casi_todo = [60.0] * 20 + [np.nan] * 4  # 20 horas válidas (>= 18)
    diaria = prepare.tabla_diaria(_crudo({"2014-01-01": casi_todo}))
    assert diaria.loc[0, "pm25"] == pytest.approx(60.0)


def test_relleno_hacia_adelante_solo_hasta_tres_horas():
    # Hueco de 3 horas: se rellena (24 horas válidas). Hueco de 4: queda 1 sin rellenar.
    hueco3 = [80.0] * 10 + [np.nan] * 3 + [80.0] * 11
    hueco4 = [80.0] * 10 + [np.nan] * 4 + [80.0] * 10
    d3 = prepare.tabla_diaria(_crudo({"2014-01-01": hueco3}))
    d4 = prepare.tabla_diaria(_crudo({"2014-01-01": hueco4}))
    assert d3.loc[0, "horas_pm25"] == 24
    assert d4.loc[0, "horas_pm25"] == 23


def test_target_es_el_dia_siguiente_de_calendario():
    crudo = _crudo({"2014-01-01": 50.0, "2014-01-02": 100.0, "2014-01-03": 40.0})
    t = prepare.construir_tabla_modelo(crudo)
    por_dia = t.set_index("fecha")["target"]
    assert por_dia[pd.Timestamp("2014-01-01")] == 1  # mañana = 100 > 75
    assert por_dia[pd.Timestamp("2014-01-02")] == 0  # mañana = 40 <= 75
    assert pd.Timestamp("2014-01-03") not in por_dia.index  # no hay mañana


def test_dia_no_valido_no_se_salta_para_calcular_el_target():
    # El 2 no es válido: el target del día 1 debe quedar vacío (no tomar el día 3).
    invalido = [90.0] * 5 + [np.nan] * 19
    crudo = _crudo({"2014-01-01": 50.0, "2014-01-02": invalido, "2014-01-03": 200.0})
    t = prepare.construir_tabla_modelo(crudo)
    assert pd.Timestamp("2014-01-01") not in set(t["fecha"])
    # El día 2 (hoy inválido) sí tiene target: mañana (día 3) es válido y supera 75
    fila = t.set_index("fecha").loc[pd.Timestamp("2014-01-02")]
    assert fila["target"] == 1
    assert np.isnan(fila["pm25"])


def test_umbral_es_estricto():
    crudo = _crudo({"2014-01-01": 10.0, "2014-01-02": config.UMBRAL_PM25})
    t = prepare.construir_tabla_modelo(crudo)
    assert t.loc[0, "target"] == 0  # exactamente 75 no supera el umbral


def test_estaciones_no_se_mezclan():
    a = _crudo({"2014-01-01": 50.0, "2014-01-02": 100.0}, estacion="A")
    b = _crudo({"2014-01-01": 50.0, "2014-01-02": 10.0}, estacion="B")
    t = prepare.construir_tabla_modelo(pd.concat([a, b], ignore_index=True))
    objetivo = t.set_index("station")["target"]
    assert objetivo["A"] == 1
    assert objetivo["B"] == 0


def test_rezagos_y_estacion_del_ano():
    crudo = _crudo({f"2014-01-0{i}": 10.0 * i for i in range(1, 5)})
    t = prepare.construir_tabla_modelo(crudo).set_index("fecha")
    fila = t.loc[pd.Timestamp("2014-01-03")]
    assert fila["pm25_lag1"] == pytest.approx(20.0)
    assert fila["pm25_lag2"] == pytest.approx(10.0)
    assert fila["estacion_ano"] == "invierno"


def _tabla_sintetica() -> pd.DataFrame:
    """Un día por fecha entre 2013-03-01 y 2017-02-27, una estación."""
    fechas = pd.date_range("2013-03-01", "2017-02-27", freq="D")
    return pd.DataFrame(
        {
            "station": "A",
            "fecha": fechas,
            "fecha_objetivo": fechas + pd.Timedelta(days=1),
            "target": np.arange(len(fechas)) % 2,
            "hoy_supera": np.arange(len(fechas)) % 2,
        }
    )


def test_split_no_se_solapa_y_respeta_el_orden():
    partes = prepare.dividir(_tabla_sintetica())
    assert partes["train"]["fecha"].max() < partes["val"]["fecha"].min()
    assert partes["val"]["fecha"].max() < partes["produccion"]["fecha"].min()


def test_split_el_target_de_cada_particion_no_sale_de_ella():
    partes = prepare.dividir(_tabla_sintetica())
    assert partes["train"]["fecha_objetivo"].max() <= pd.Timestamp(config.TRAIN_FIN)
    assert partes["val"]["fecha_objetivo"].max() <= pd.Timestamp(config.VAL_FIN)
    assert partes["produccion"]["fecha_objetivo"].max() <= pd.Timestamp(
        config.PRODUCCION_FIN
    )
    assert partes["train"]["fecha"].min() >= pd.Timestamp(config.TRAIN_INICIO)


def test_split_usa_fechas_fijas_no_azar():
    t = _tabla_sintetica()
    a = prepare.dividir(t)
    b = prepare.dividir(t.sample(frac=1, random_state=1))  # mismo contenido, otro orden
    for nombre in a:
        assert set(a[nombre]["fecha"]) == set(b[nombre]["fecha"])


def test_baseline_repite_la_clase_de_hoy():
    t = pd.DataFrame({"hoy_supera": [1.0, 0.0, np.nan, 1.0]})
    assert prepare.baseline_persistencia(t).tolist()[:2] == [1.0, 0.0]


def test_metricas_ignoran_filas_sin_prediccion():
    real = pd.Series([1, 1, 0, 0, 1])
    pred = pd.Series([1.0, 0.0, 0.0, np.nan, 1.0])
    m = prepare.metricas(real, pred)
    assert m["n"] == 4
    assert m["sensibilidad"] == pytest.approx(2 / 3)  # 2 de 3 días malos detectados
    assert m["precision"] == pytest.approx(1.0)  # todo lo que avisó era real


def test_metricas_por_estacion_devuelve_una_fila_por_estacion():
    t = pd.DataFrame({"station": ["A", "A", "B", "B"], "target": [1, 0, 1, 0]})
    pred = pd.Series([1.0, 0.0, 0.0, 0.0])
    m = prepare.metricas_por_estacion(t, pred)
    assert set(m.index) == {"A", "B"}
    assert m.loc["A", "sensibilidad"] == 1.0
    assert m.loc["B", "sensibilidad"] == 0.0
