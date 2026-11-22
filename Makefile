setup:
	uv sync

smoke:
	uv run python -m proyecto_1_esp_data.smoke

data:
	uv run python -m proyecto_1_esp_data.data.download

drift:
	uv run python -m proyecto_1_esp_data.monitoring.drift

drift-check:
	uv run python -m proyecto_1_esp_data.monitoring.drift --check

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint test

.PHONY: setup smoke data drift drift-check test lint format check

pipeline:
	uv run python -m proyecto_1_esp_data.pipeline.flow

pipeline-cache:
	uv run python -m proyecto_1_esp_data.pipeline.flow --medir-cache

serve:
	uv run python -m proyecto_1_esp_data.pipeline.flow --servir

.PHONY: pipeline pipeline-cache serve


# --- Modelo y apps ---------------------------------------------------------------
# `make train` descarga los datos solo si faltan y luego entrena; `make app` y
# `make api` entrenan solo si todavía no hay modelo guardado.
DATOS := data/raw/calidad_aire_beijing.csv
MODELO := models/clasificador_pm25.joblib

$(DATOS):
	uv run python -m proyecto_1_esp_data.data.download

$(MODELO): $(DATOS)
	uv run python -m proyecto_1_esp_data.train

train: $(DATOS)
	uv run python -m proyecto_1_esp_data.train

app: $(MODELO)
	uv run streamlit run app/streamlit_app.py

api: $(MODELO)
	uv run uvicorn app.api_fastapi:app --reload

.PHONY: train app api
