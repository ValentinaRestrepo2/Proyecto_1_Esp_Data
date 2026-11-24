from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from proyecto_1_esp_data import predict
from proyecto_1_esp_data.predict import predecir

MENSAJE_SIN_MODELO = "El modelo no está disponible todavía."
MENSAJE_ENTRADA_INVALIDA = "Los datos de entrada no son válidos."

EJEMPLO = {
    "pm25": 80.0,
    "PM10": 120.0,
    "SO2": 10.0,
    "NO2": 45.0,
    "CO": 900.0,
    "O3": 40.0,
    "TEMP": 5.0,
    "PRES": 1020.0,
    "DEWP": -10.0,
    "RAIN": 0.0,
    "WSPM": 2.5,
    "pm25_lag1": 70.0,
    "pm25_lag2": 65.0,
    "wd": "NW",
    "station": "Aotizhongxin",
    "estacion_ano": "invierno",
}


class Entrada(BaseModel):
    """Variables del día de hoy. Los valores numéricos pueden ser null (faltantes)."""

    model_config = ConfigDict(json_schema_extra={"example": EJEMPLO})

    pm25: float | None = Field(None, description="PM2.5 medio de hoy (µg/m³)")
    PM10: float | None = Field(None, description="PM10 medio de hoy (µg/m³)")
    SO2: float | None = Field(None, description="SO₂ medio de hoy")
    NO2: float | None = Field(None, description="NO₂ medio de hoy")
    CO: float | None = Field(None, description="CO medio de hoy")
    O3: float | None = Field(None, description="O₃ medio de hoy")
    TEMP: float | None = Field(None, description="Temperatura (°C)")
    PRES: float | None = Field(None, description="Presión atmosférica (hPa)")
    DEWP: float | None = Field(None, description="Punto de rocío (°C)")
    RAIN: float | None = Field(None, description="Lluvia (mm)")
    WSPM: float | None = Field(None, description="Velocidad del viento (m/s)")
    pm25_lag1: float | None = Field(None, description="PM2.5 de ayer (µg/m³)")
    pm25_lag2: float | None = Field(None, description="PM2.5 de antier (µg/m³)")
    wd: str = Field(..., description="Dirección del viento (16 puntos)")
    station: str = Field(..., description="Estación de monitoreo")
    estacion_ano: str = Field(..., description="invierno, primavera, verano u otono")


class Respuesta(BaseModel):
    probabilidad_pm25_mala_manana: float = Field(
        ..., description="Probabilidad (0 a 1) de que mañana el PM2.5 supere el umbral"
    )
    mala_calidad_manana: bool
    umbral_pm25: float


app = FastAPI(
    title="Calidad del aire · Beijing",
    description="Predice si mañana el PM2.5 medio superará 75 µg/m³ en una estación.",
    version="0.1.0",
)


@app.get("/health", summary="Estado del servicio")
def salud() -> dict:
    disponible = predict.modelo_disponible()
    return {
        "estado": "ok",
        "modelo_disponible": disponible,
        # Versión del modelo vigente en el registro: permite saber qué está sirviendo
        "version_modelo": predict.version_modelo(),
    }


@app.post(
    "/predict",
    response_model=Respuesta,
    summary="Predice la calidad del aire de mañana",
)
def predecir_endpoint(entrada: Entrada) -> dict:
    try:
        return predecir(entrada.model_dump())
    except FileNotFoundError as e:
        # 503: el servicio está arriba, pero aún no hay un modelo vigente. El mensaje
        # es fijo: str(e) podría filtrar rutas o detalles internos al cliente.
        raise HTTPException(status_code=503, detail=MENSAJE_SIN_MODELO) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=MENSAJE_ENTRADA_INVALIDA) from e
