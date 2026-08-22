"""
Estado conversacional temporal.

Hackathon:
    memoria RAM.

Producción:
    Redis / almacenamiento temporal con TTL.
"""

from copy import deepcopy
from threading import Lock


_SESIONES = {}
_LOCK = Lock()


def obtener_sesion(
    usuario_id: str,
):
    with _LOCK:
        estado = _SESIONES.get(
            usuario_id
        )

        if estado is None:
            estado = {
                "usuario_id":
                    usuario_id,

                "mensajes":
                    [],

                "datos":
                    {},

                "triage":
                    {},

                "ruta":
                    None,

                "fase":
                    "triage",
            }

            _SESIONES[
                usuario_id
            ] = estado

        return deepcopy(
            estado
        )


def guardar_sesion(
    usuario_id: str,
    estado: dict,
):
    with _LOCK:

        _SESIONES[
            usuario_id
        ] = deepcopy(
            estado
        )


def borrar_sesion(
    usuario_id: str,
):
    with _LOCK:

        _SESIONES.pop(
            usuario_id,
            None,
        )