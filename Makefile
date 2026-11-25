# Comandos del proyecto. Corre `make` sin argumentos para ver la ayuda.
# Todos los objetivos van en .PHONY: `app/` y `data/` son carpetas del repo y
# sin esto make las tomaría como archivos ya existentes.
.DEFAULT_GOAL := help
.PHONY: help setup data test lint format check train app api clean

help:
	@echo "Comandos del proyecto:"
	@echo "  setup     instala las dependencias (uv sync)"
	@echo "  data      descarga y verifica los datos de UCI"
	@echo "  train     entrena el modelo (descarga los datos si faltan)"
	@echo "  app       abre la app de Streamlit (entrena si no hay modelo)"
	@echo "  api       levanta la API; documentación en /docs"
	@echo "  test      corre las pruebas"
	@echo "  lint      revisa el estilo con ruff"
	@echo "  format    da formato con ruff"
	@echo "  check     lint + test"
	@echo "  clean     borra cachés y el modelo entrenado"

setup:
	uv sync

data:
	uv run python -m proyecto_1_esp_data.data.download

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint test

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

# Multiplataforma: `find` y `rm` no existen en el cmd de Windows, por eso se usa Python.
clean:
	uv run python -c "import os, shutil; [shutil.rmtree(os.path.join(d, n), ignore_errors=True) for d, ns, _ in os.walk('.') if '.venv' not in d for n in ns if n in ('__pycache__', '.pytest_cache', '.ruff_cache')]; os.path.exists('models/clasificador_pm25.joblib') and os.remove('models/clasificador_pm25.joblib')"