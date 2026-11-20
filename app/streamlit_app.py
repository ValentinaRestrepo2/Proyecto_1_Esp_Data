import streamlit as st
from proyecto_1_esp_data import config
from proyecto_1_esp_data.predict import predecir

st.set_page_config(
    page_title="Calidad del aire · Beijing",
    page_icon="🌫️",
    layout="wide",
)

# clave: (etiqueta, unidad, mínimo, valor inicial). Mínimo None admite negativos.
CAMPOS = {
    "pm25": ("PM2.5 promedio de hoy", "µg/m³", 0.0, 60.0),
    "PM10": ("PM10", "µg/m³", 0.0, 100.0),
    "SO2": ("SO₂", "µg/m³", 0.0, 15.0),
    "NO2": ("NO₂", "µg/m³", 0.0, 40.0),
    "CO": ("CO", "µg/m³", 0.0, 900.0),
    "O3": ("O₃", "µg/m³", 0.0, 50.0),
    "TEMP": ("Temperatura", "°C", None, 5.0),
    "PRES": ("Presión atmosférica", "hPa", 900.0, 1020.0),
    "DEWP": ("Punto de rocío", "°C", None, -10.0),
    "RAIN": ("Lluvia", "mm", 0.0, 0.0),
    "WSPM": ("Velocidad del viento", "m/s", 0.0, 2.5),
    "pm25_lag1": ("PM2.5 de ayer", "µg/m³", 0.0, 70.0),
    "pm25_lag2": ("PM2.5 de antier", "µg/m³", 0.0, 65.0),
}

NOMBRES_ESTACION_ANO = {
    "invierno": "Invierno",
    "primavera": "Primavera",
    "verano": "Verano",
    "otono": "Otoño",
}

LOGO = (
    '<svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#ffffff" '
    'stroke-width="1.8" stroke-linecap="round">'
    '<path d="M3 8h11a3 3 0 1 0-3-3"/><path d="M3 12h15a3 3 0 1 1-3 3"/>'
    '<path d="M3 16h7"/></svg>'
)

ESTILO = """
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.hero {display: flex; align-items: center; gap: 1.25rem;
  background: linear-gradient(135deg, #0f766e 0%, #0e7490 60%, #155e75 100%);
  padding: 1.5rem 2rem; border-radius: 18px; margin-bottom: 1.5rem;
  box-shadow: 0 10px 30px rgba(14, 116, 144, 0.30);}
.hero h1 {color: #ffffff; font-size: 1.8rem; font-weight: 700; margin: 0;}
.hero p {color: #e0f2fe; margin: 0.3rem 0 0 0;}
.seccion {font-size: 1.05rem; font-weight: 700; color: #0f766e;
  margin: 1.2rem 0 0.4rem 0;}
.tarjeta {background: #ffffff; color: #0f172a; border: 1px solid #e2e8f0;
  border-radius: 16px; padding: 1.5rem;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);}
.centrada {text-align: center;}
.pct {font-size: 3.2rem; font-weight: 800; line-height: 1.1;}
.nivel {font-size: 1.1rem; font-weight: 600; margin: 0.25rem 0 0.75rem 0;}
.texto {color: #475569; margin: 0.5rem 0 0 0;}
div[data-testid="stFormSubmitButton"] button {
  background: linear-gradient(135deg, #0f766e, #0e7490); color: #ffffff;
  border: none; border-radius: 999px; padding: 0.7rem 1.5rem; font-weight: 600;
  width: 100%; box-shadow: 0 6px 16px rgba(14, 116, 144, 0.35);
  transition: transform 0.15s ease;}
div[data-testid="stFormSubmitButton"] button:hover {
  transform: translateY(-2px); color: #ffffff;}
</style>
"""


def campo(columna, clave: str) -> float:
    etiqueta, unidad, minimo, inicial = CAMPOS[clave]
    return columna.number_input(
        f"{etiqueta} ({unidad})",
        min_value=minimo,
        value=inicial,
        step=1.0,
        format="%.1f",
        key=clave,
    )


def titulo(texto: str) -> None:
    st.markdown(f'<div class="seccion">{texto}</div>', unsafe_allow_html=True)


def mostrar_resultado(r: dict) -> None:
    p = r["probabilidad_pm25_mala_manana"]
    if r["mala_calidad_manana"]:
        etiqueta, color = "Mala calidad anticipada", "#b91c1c"
    elif p >= 0.35:
        etiqueta, color = "Vigilar: riesgo moderado", "#b45309"
    else:
        etiqueta, color = "Calidad aceptable", "#15803d"

    st.markdown(
        f'<div class="tarjeta centrada">'
        f'<div class="pct" style="color:{color}">{p:.0%}</div>'
        f'<div class="nivel" style="color:{color}">{etiqueta}</div>'
        f'<p class="texto">Probabilidad de que mañana el PM2.5 supere '
        f"{config.UMBRAL_PM25:.0f} µg/m³ en esta estación.</p>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.progress(p)


st.markdown(ESTILO, unsafe_allow_html=True)
st.markdown(
    f'<div class="hero">{LOGO}<div>'
    "<h1>Calidad del aire · Beijing</h1>"
    "<p>¿Superará mañana el PM2.5 los 75 µg/m³ en esta estación de monitoreo?</p>"
    "</div></div>",
    unsafe_allow_html=True,
)

izquierda, derecha = st.columns([2, 1], gap="large")
datos: dict = {}

with izquierda:
    with st.form("entrada"):
        titulo("🧪 Contaminantes de hoy")
        for claves in (["pm25", "PM10", "SO2"], ["NO2", "CO", "O3"]):
            for col, clave in zip(st.columns(3), claves):
                datos[clave] = campo(col, clave)

        titulo("🌬️ Meteorología de hoy")
        for claves in (["TEMP", "PRES", "DEWP"], ["RAIN", "WSPM"]):
            for col, clave in zip(st.columns(3), claves):
                datos[clave] = campo(col, clave)

        titulo("📅 Historial reciente")
        cols = st.columns(3)
        datos["pm25_lag1"] = campo(cols[0], "pm25_lag1")
        datos["pm25_lag2"] = campo(cols[1], "pm25_lag2")

        titulo("📍 Contexto")
        cols = st.columns(3)
        datos["station"] = cols[0].selectbox("Estación", config.ESTACIONES, key="station")
        datos["wd"] = cols[1].selectbox(
            "Dirección del viento", config.DIRECCIONES_VIENTO, key="wd"
        )
        datos["estacion_ano"] = cols[2].selectbox(
            "Estación del año",
            config.ESTACIONES_DEL_ANO,
            format_func=NOMBRES_ESTACION_ANO.get,
            key="estacion_ano",
        )

        enviado = st.form_submit_button("Predecir calidad del aire de mañana")

with derecha:
    titulo("📊 Resultado")
    if not enviado:
        st.markdown(
            '<div class="tarjeta centrada">'
            '<div class="pct" style="color:#64748b">—</div>'
            '<p class="texto">Completa los datos y pulsa <b>Predecir</b> '
            "para ver el resultado.</p></div>",
            unsafe_allow_html=True,
        )
    else:
        try:
            mostrar_resultado(predecir(datos))
        except FileNotFoundError as e:
            st.error(str(e))
        except ValueError as e:
            st.error(f"Revisa los datos: {e}")

st.caption(
    "Modelo LightGBM entrenado con datos de 2013-2014 y validado en 2015. "
    "Herramienta de apoyo: no sustituye los reportes oficiales de calidad del aire."
)