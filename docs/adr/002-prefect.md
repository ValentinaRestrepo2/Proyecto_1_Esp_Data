# ADR 002: Orquestación con Prefect

- **Estado:** aceptada (2026-11-08)
- **Relacionadas:** [ADR 000](000-stack.md), [política de reentrenamiento](../politica-de-reentrenamiento.md)

## Contexto

Hay que ejecutar siempre los mismos pasos (descargar, validar, preparar, medir drift, entrenar, evaluar, registrar) y poder repetirlos cada trimestre sin intervención manual, pero sin que una máquina decida sola qué modelo usa.

## Decisión

Un flujo de Prefect 3 (`pipeline/flow.py`) con 11 tareas. El grafo sale de las dependencias de datos.

| Aspecto | Decisión | Razón |
|---|---|---|
| Reintentos | Solo en `asegurar_datos`, 3 intentos, espera de 10 s con backoff exponencial y jitter, y solo ante `requests.RequestException` | Es la única tarea con red. Reintentar un hash distinto o un contrato roto no lo arregla y ocultaría el error |
| Caché | `cache_key_fn` en tabla diaria y drift; llave = hash del CSV + umbrales + código del módulo | Un caché que ignora el código devuelve resultados viejos tras un cambio de lógica; uno que ignora los datos, también |
| Medición del caché | `make pipeline-cache` (dos corridas, la primera sin caché por una sal aleatoria) | Se reporta el efecto real: 3,2 a 3,4 veces más rápido en los datos reales |
| Schedule | Cron trimestral `0 6 1 1,4,7,10 *`, `America/Bogota`, con `flujo.serve` | Mismo ritmo que la política de reentrenamiento; correr cada pocos minutos no tendría sentido con datos que no cambian |
| Promoción | El flujo no promueve: escribe `candidato.json` con `promovido: false` | Promover es decisión de una persona (política, sección 4) |
| Modelos | Un registro `ENTRENADORES`; cada uno devuelve un `Candidato` con su función `predecir` | Agregar LightGBM es una función nueva, sin tocar el flujo |
| Almacenamiento local | Resultados en `.prefect_cache/` (no se versiona) y base SQLite propia de Prefect | Sin servidor externo: funciona con un comando en una máquina limpia |

## Alternativas

- **Airflow:** exige servidor y base de datos para 11 pasos. Descartada (ADR 000).
- **Un script secuencial con `make`:** reproduce los pasos pero no da reintentos, caché con llave ni artifacts visibles.
- **Caché por fecha del archivo:** se invalida al copiar el CSV aunque sea idéntico. El hash identifica el contenido.

## Consecuencias

- Se agrega la dependencia `prefect`, que arrastra varias librerías; se fija en `uv.lock`.
- Prefect crea una base SQLite en su carpeta de usuario; se desactiva su telemetría para evitar bloqueos de la base.
- El drift (la tarea más lenta) queda cacheado: si se quiere forzarlo, se borra `.prefect_cache/`.
