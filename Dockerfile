# syntax=docker/dockerfile:1
# Imagen de la API de calidad del aire (FastAPI).
#
# Etapa 1 (builder): instala las dependencias exactas de uv.lock.
# Etapa 2 (runtime): copia solo el entorno ya construido, descarga los datos,
#   entrena y pasa el candidato por la compuerta de promoción. Si la compuerta
#   rechaza el modelo, el build FALLA: no existe una imagen con un modelo no
#   aprobado. Corre sin root y tiene healthcheck.
#
# Construir:  docker build -t calidad-aire .
# Ejecutar:   docker run --rm -p 8000:8000 calidad-aire

# ---- Etapa 1: dependencias ------------------------------------------------------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Primero solo los archivos de dependencias: esta capa se reutiliza mientras
# uv.lock no cambie, aunque cambie el código.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---- Etapa 2: ejecución -----------------------------------------------------------
FROM python:3.12-slim AS runtime

# LightGBM necesita la librería OpenMP del sistema.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios (UID fijo para poder verificarlo).
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
# La app escribe aquí el registro de MLflow y los reportes durante el build.
RUN chown appuser:appuser /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser data/raw/metadata.json ./data/raw/metadata.json

USER appuser

# Quién aprueba la promoción dentro del build. La compuerta se aplica igual.
ARG APROBADOR=build-docker

# Datos (descarga y verificación de hash), entrenamiento y promoción.
RUN python -m proyecto_1_esp_data.data.download \
    && python -m proyecto_1_esp_data.train \
    && python -m proyecto_1_esp_data.promocion --aprobador "${APROBADOR}" \
    && rm -rf data/raw/*.zip

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "app.api_fastapi:app", "--host", "0.0.0.0", "--port", "8000"]
