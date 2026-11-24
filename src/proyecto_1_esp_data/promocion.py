"""Compuerta de promoción: decide si un candidato pasa a ser el modelo vigente.

El entrenamiento deja un candidato (alias `candidate`). Esta compuerta lo compara con
la línea base y con el modelo vigente, y solo si cumple todas las reglas mueve el alias
`champion`, que es lo que cargan la API y la app. Cada decisión, aprobada o rechazada,
queda en `reports/promociones.json` con las métricas, las reglas y quién la tomó, y en
las etiquetas de la versión en MLflow.

Es un paso aparte y explícito (lo corre una persona, con su nombre) porque la política
de reentrenamiento exige un aprobador. Las reglas son una función pura (`decidir`), así
que se prueban sin MLflow.

Uso:
    uv run python -m proyecto_1_esp_data.promocion --aprobador "Santiago"
    uv run python -m proyecto_1_esp_data.promocion --aprobador "Santiago" --volver-a 2
Sale con código 0 si promueve y 1 si rechaza, igual que `drift --check`.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from proyecto_1_esp_data import config, registro


@dataclass(frozen=True)
class Decision:
    aprobado: bool
    # Cada regla evaluada: {"regla": texto, "cumple": bool, "detalle": texto}
    comprobaciones: list[dict] = field(default_factory=list)

    @property
    def razones_de_rechazo(self) -> list[str]:
        return [
            f"{c['regla']}: {c['detalle']}"
            for c in self.comprobaciones
            if not c["cumple"]
        ]


def _regla(regla: str, cumple: bool, detalle: str) -> dict:
    return {"regla": regla, "cumple": bool(cumple), "detalle": detalle}


def decidir(
    candidato: dict,
    linea_base: dict,
    vigente: dict | None,
    precision_minima: float = config.PRECISION_MINIMA,
) -> Decision:
    """Reglas de promoción. Cada argumento es {"val": {...}, "produccion": {...}}.

    1. Supera a la línea base en sensibilidad, en validación y en producción simulada
       (si no le gana a "mañana = hoy", no vale la pena servirlo).
    2. Precisión en validación >= la mínima (la sensibilidad no se logra avisando todos
       los días).
    3. Si ya hay modelo vigente, supera su sensibilidad en validación de forma estricta
       (un candidato igual no justifica cambiar lo que está en producción).
    """
    comprobaciones = []
    for particion in registro.PARTICIONES:
        c = candidato[particion]["sensibilidad"]
        b = linea_base[particion]["sensibilidad"]
        comprobaciones.append(
            _regla(
                f"Sensibilidad en {particion} supera a la línea base",
                c > b,
                f"candidato {c:.3f} frente a línea base {b:.3f}",
            )
        )
    p = candidato["val"]["precision"]
    comprobaciones.append(
        _regla(
            "Precisión en val alcanza la mínima",
            p >= precision_minima,
            f"candidato {p:.3f}, mínima {precision_minima:.3f}",
        )
    )
    if vigente is not None:
        c = candidato["val"]["sensibilidad"]
        v = vigente["val"]["sensibilidad"]
        comprobaciones.append(
            _regla(
                "Sensibilidad en val supera al modelo vigente",
                c > v,
                f"candidato {c:.3f} frente a vigente {v:.3f}",
            )
        )
    return Decision(
        aprobado=all(c["cumple"] for c in comprobaciones),
        comprobaciones=comprobaciones,
    )


def _agregar_al_reporte(entrada: dict, ruta: Path | None) -> None:
    """Agrega la decisión al historial (lista JSON, versionada en Git)."""
    ruta = ruta or config.REPORTE_PROMOCIONES  # se lee al llamar, no al definir
    historial = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []
    historial.append(entrada)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(historial, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def promover(
    aprobador: str,
    version: str | None = None,
    ruta_reporte: Path | None = None,
) -> dict:
    """Evalúa un candidato (por defecto el alias `candidate`) y lo promueve si cumple."""
    client = registro.cliente()
    candidato = (
        client.get_model_version(config.MODELO_REGISTRADO, str(version))
        if version
        else registro.version_por_alias(client, config.ALIAS_CANDIDATO)
    )
    if candidato is None:
        raise LookupError("No hay candidato. Corre `make train` primero.")

    vigente = registro.version_por_alias(client, config.ALIAS_VIGENTE)
    version_candidata = str(candidato.version)  # MLflow la entrega como entero
    version_anterior = str(vigente.version) if vigente else None
    if version_candidata == version_anterior:
        raise ValueError(f"La versión {version_candidata} ya es el modelo vigente.")

    metricas = registro.metricas_de_version(client, candidato)
    metricas_vigente = (
        registro.metricas_de_version(client, vigente)["modelo"] if vigente else None
    )
    decision = decidir(metricas["modelo"], metricas["linea_base"], metricas_vigente)

    nombre = config.MODELO_REGISTRADO
    estado = "aprobado" if decision.aprobado else "rechazado"
    client.set_model_version_tag(nombre, version_candidata, "validation_status", estado)
    client.set_model_version_tag(nombre, version_candidata, "decidido_por", aprobador)
    if not decision.aprobado:
        client.set_model_version_tag(
            nombre,
            version_candidata,
            "razones_de_rechazo",
            " | ".join(decision.razones_de_rechazo),
        )
    else:
        client.set_registered_model_alias(
            nombre, config.ALIAS_VIGENTE, version_candidata
        )
        # `candidate` solo se libera si apuntaba a esta versión: si se evaluó otra de
        # forma explícita, el candidato más reciente sigue esperando su turno.
        pendiente = registro.version_por_alias(client, config.ALIAS_CANDIDATO)
        if pendiente is not None and str(pendiente.version) == version_candidata:
            client.delete_registered_model_alias(nombre, config.ALIAS_CANDIDATO)

    entrada = {
        "fecha_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "accion": "promocion",
        "version": version_candidata,
        "decision": estado,
        "decidido_por": aprobador,
        "version_anterior": version_anterior,
        "razones_de_rechazo": decision.razones_de_rechazo,
        "comprobaciones": decision.comprobaciones,
        "metricas_candidato": metricas["modelo"],
        "metricas_linea_base": metricas["linea_base"],
        "metricas_vigente": metricas_vigente,
        "huella_datos_sha256": candidato.tags.get("huella_datos_sha256"),
        "run_id": candidato.run_id,
    }
    _agregar_al_reporte(entrada, ruta_reporte)
    return entrada


def volver_a(version: str, aprobador: str, ruta_reporte: Path | None = None) -> dict:
    """Rollback: mueve `champion` a una versión anterior, sin reentrenar."""
    client = registro.cliente()
    destino = client.get_model_version(config.MODELO_REGISTRADO, str(version))
    vigente = registro.version_por_alias(client, config.ALIAS_VIGENTE)
    client.set_registered_model_alias(
        config.MODELO_REGISTRADO, config.ALIAS_VIGENTE, str(destino.version)
    )
    entrada = {
        "fecha_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "accion": "rollback",
        "version": str(destino.version),
        "decision": "aprobado",
        "decidido_por": aprobador,
        "version_anterior": str(vigente.version) if vigente else None,
        "run_id": destino.run_id,
    }
    _agregar_al_reporte(entrada, ruta_reporte)
    return entrada


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compuerta de promoción del modelo")
    parser.add_argument("--aprobador", required=True, help="quién toma la decisión")
    parser.add_argument(
        "--version", help="versión a evaluar (por defecto, el candidato)"
    )
    parser.add_argument(
        "--volver-a", help="rollback: versión que vuelve a ser la vigente"
    )
    args = parser.parse_args(argv)

    if args.volver_a:
        entrada = volver_a(args.volver_a, args.aprobador)
        print(f"Rollback: la versión vigente ahora es la {entrada['version']}.")
        return 0

    entrada = promover(args.aprobador, args.version)
    for c in entrada["comprobaciones"]:
        marca = "cumple " if c["cumple"] else "NO CUMPLE"
        print(f"  [{marca}] {c['regla']}: {c['detalle']}")
    if entrada["decision"] == "aprobado":
        print(f"PROMOVIDO: la versión {entrada['version']} es ahora el modelo vigente.")
        return 0
    print(
        f"RECHAZADO: la versión {entrada['version']} no se promueve; "
        f"queda el modelo vigente anterior ({entrada['version_anterior']})."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
