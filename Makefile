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
# `make train` descarga los datos si faltan y registra un CANDIDATO en MLflow: no cambia
# el modelo vigente. `make promote` lo pasa por la compuerta de promoción. `make app` y
# `make api` sirven el modelo vigente (alias champion); si no hay, avisan que corras
# primero `make train` y `make promote`.
DATOS := data/raw/calidad_aire_beijing.csv

$(DATOS):
	uv run python -m proyecto_1_esp_data.data.download

train: $(DATOS)
	uv run python -m proyecto_1_esp_data.train

promote:
	@test -n "$(APROBADOR)" || (echo "Usa: make promote APROBADOR=tu-nombre" && exit 1)
	uv run python -m proyecto_1_esp_data.promocion --aprobador "$(APROBADOR)"

mlflow-ui:
	uv run mlflow ui --backend-store-uri sqlite:///mlflow.db

app:
	uv run streamlit run app/streamlit_app.py

api:
	uv run uvicorn app.api_fastapi:app --reload

.PHONY: train promote mlflow-ui model-card app api

model-card:
	uv run python -m proyecto_1_esp_data.model_card
