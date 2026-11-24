# Contrato de la API

Servicio FastAPI (`app/api_fastapi.py`). La documentación interactiva se genera sola en `/docs` y el esquema en `/openapi.json`. Este archivo fija lo que el servicio promete a quien lo consuma.

**Cómo se levanta:** `make api` (desarrollo) o la imagen Docker (`docker run --rm -p 8000:8000 calidad-aire`). Para servir una predicción hace falta un modelo vigente en el registro (`make train` y `make promote APROBADOR=<nombre>`); la imagen Docker ya lo trae.

Versión de la API: 0.1.0. Sin autenticación: pensada para uso local y de demostración.

## `GET /health`

Estado del servicio. Responde 200 aunque no haya modelo, para saber si el servicio está vivo y qué modelo sirve.

```json
{ "estado": "ok", "modelo_disponible": true, "version_modelo": "1" }
```

| Campo | Tipo | Significado |
|---|---|---|
| `estado` | texto | Siempre `"ok"` si el servicio responde |
| `modelo_disponible` | booleano | Hay un modelo con alias `champion` en el registro |
| `version_modelo` | texto o `null` | Versión del modelo vigente; `null` si no hay |

Es el endpoint que usa el `HEALTHCHECK` de Docker.

## `POST /predict`

Predice si **mañana** el PM2.5 medio superará el umbral (75 µg/m³) en una estación, con las variables de **hoy**.

### Entrada (JSON)

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `pm25` | número o `null` | no | PM2.5 medio de hoy (µg/m³) |
| `PM10`, `SO2`, `NO2`, `CO`, `O3` | número o `null` | no | Medias de hoy de cada contaminante |
| `TEMP` | número o `null` | no | Temperatura (°C) |
| `PRES` | número o `null` | no | Presión (hPa) |
| `DEWP` | número o `null` | no | Punto de rocío (°C) |
| `RAIN` | número o `null` | no | Lluvia (mm) |
| `WSPM` | número o `null` | no | Velocidad del viento (m/s) |
| `pm25_lag1` | número o `null` | no | PM2.5 de ayer |
| `pm25_lag2` | número o `null` | no | PM2.5 de antier |
| `wd` | texto | **sí** | Dirección del viento (N, NNE, NE, ..., NNW; 16 puntos) |
| `station` | texto | **sí** | Una de las 12 estaciones del dataset (por ejemplo `Aotizhongxin`) |
| `estacion_ano` | texto | **sí** | `invierno`, `primavera`, `verano` u `otono` (sin ñ) |

Los numéricos pueden omitirse o ir en `null`: el modelo los imputa con la mediana de entrenamiento.

Ejemplo:

```json
{
  "pm25": 80.0, "PM10": 120.0, "SO2": 10.0, "NO2": 45.0, "CO": 900.0, "O3": 40.0,
  "TEMP": 5.0, "PRES": 1020.0, "DEWP": -10.0, "RAIN": 0.0, "WSPM": 2.5,
  "pm25_lag1": 70.0, "pm25_lag2": 65.0,
  "wd": "NW", "station": "Aotizhongxin", "estacion_ano": "invierno"
}
```

### Respuesta 200

```json
{ "probabilidad_pm25_mala_manana": 0.2383, "mala_calidad_manana": false, "umbral_pm25": 75.0 }
```

| Campo | Tipo | Significado |
|---|---|---|
| `probabilidad_pm25_mala_manana` | número entre 0 y 1 | Probabilidad estimada de superar el umbral |
| `mala_calidad_manana` | booleano | `true` si la probabilidad alcanza el umbral de decisión del modelo (0,5) |
| `umbral_pm25` | número | Umbral de PM2.5 del problema (75 µg/m³) |

### Errores

| Código | Cuándo | Cuerpo |
|---|---|---|
| 422 | Falta un campo obligatorio o un tipo es incorrecto (por ejemplo `pm25: "abc"`) | Formato estándar de FastAPI: `{"detail": [{"loc": [...], "msg": "..."}]}` |
| 422 | El modelo rechaza los datos de entrada | `{"detail": "Los datos de entrada no son válidos."}` |
| 503 | No hay modelo vigente en el registro | `{"detail": "El modelo no está disponible todavía."}` |

Los mensajes 422 del modelo y 503 son fijos a propósito: no exponen rutas ni detalles internos.

## Lo que el contrato no garantiza

- **Valores categóricos desconocidos.** Una `station` que no existe (por ejemplo `"Marte"`) no da error: el codificador la ignora y responde con una predicción sin información de estación. Quien consuma la API debe validar el nombre.
- **Rangos físicos.** La API no comprueba que los valores sean plausibles (el contrato de rangos aplica a los datos de entrenamiento, no a las peticiones).
- **Calidad de la predicción.** Los límites del modelo están en [`model-card.md`](model-card.md).
- **Latencia o disponibilidad.** No hay medición ni compromiso de nivel de servicio.

## Pruebas

`tests/test_api.py` verifica `/health` con y sin modelo, el 200 con la forma de la respuesta, los nulos, el 422 por campo faltante y el 503 con mensaje fijo.
