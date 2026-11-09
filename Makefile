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
