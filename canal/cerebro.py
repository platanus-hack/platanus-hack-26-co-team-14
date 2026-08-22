"""
El backend, visto desde el puente.

El puente manda siempre el mismo sobre —lo diga la usuaria hablando o
escribiendo— y espera siempre la misma respuesta:

    entra   {"telefono", "texto", "tipo", "transcripcion", ...}
    sale    {"responder": [ {"tipo": "texto"|"audio"|"documento", ...} ]}

Ese contrato está descrito en puente/README.md, y es el mismo tanto si el
puente llama por HTTP a otro servicio como si llama aquí, en el mismo proceso.
Este módulo es lo segundo: traduce el sobre a un turno de conversación y
devuelve lo que el orquestador decidió decir.

No decide nada por su cuenta. Es una aduana.
"""

from __future__ import annotations

import logging

from canal.orquestador import procesar_turno

log = logging.getLogger("cerebro")


def responder(mensaje: dict) -> list[dict]:
    """Implementa `POST /mensaje`. Devuelve la lista de acciones."""
    telefono = str(mensaje.get("telefono") or "").strip()

    if not telefono:
        log.warning("mensaje sin teléfono: %s", str(mensaje)[:200])
        return []

    texto = (mensaje.get("texto") or "").strip()
    transcripcion = mensaje.get("transcripcion") or None

    log.info("turno de %s (%s): %s", telefono, mensaje.get("tipo"), texto[:120])

    acciones = procesar_turno(telefono, texto, transcripcion=transcripcion)

    log.info("respondo con %d acción(es): %s",
             len(acciones), [a.get("tipo") for a in acciones])

    return acciones


def conectar() -> None:
    """Enchufa este backend al puente, sin salto HTTP.

    Solo si no hay BACKEND_URL: una URL configurada gana siempre, para poder
    apuntar el puente a otro backend sin tocar código.
    """
    from puente import backend, config

    if config.BACKEND_URL:
        log.info("BACKEND_URL definido (%s): el puente no usará el cerebro "
                 "en proceso", config.BACKEND_URL)
        return

    backend.registrar_local(responder)
