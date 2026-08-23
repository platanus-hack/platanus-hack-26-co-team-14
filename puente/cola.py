"""Cola concurrente: paralelismo entre teléfonos y orden dentro de cada chat."""

from __future__ import annotations

import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Callable

from . import config

log = logging.getLogger("cola")

_lock = Lock()
_executor: ThreadPoolExecutor | None = None
_colas: dict[str, deque[tuple[Callable, dict]]] = {}
_activos: set[str] = set()
_pendientes = 0


def iniciar() -> None:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=config.PROCESADORES_CONCURRENTES,
                thread_name_prefix="temis",
            )


def encolar(funcion: Callable[[dict], None], mensaje: dict) -> bool:
    """Encola sin bloquear. Devuelve False si se alcanzó el límite global."""
    global _pendientes
    telefono = str(mensaje.get("telefono") or "").strip()
    if not telefono:
        return False

    iniciar()
    with _lock:
        if _pendientes >= config.COLA_MAX_MENSAJES:
            log.error("cola llena; se rechazó un mensaje para %s", telefono)
            return False
        cola = _colas.setdefault(telefono, deque())
        cola.append((funcion, mensaje))
        _pendientes += 1
        if telefono in _activos:
            return True
        _activos.add(telefono)
        assert _executor is not None
        _executor.submit(_procesar_telefono, telefono)
    return True


def _procesar_telefono(telefono: str) -> None:
    global _pendientes
    while True:
        with _lock:
            cola = _colas.get(telefono)
            if not cola:
                _colas.pop(telefono, None)
                _activos.discard(telefono)
                return
            funcion, mensaje = cola.popleft()
        try:
            funcion(mensaje)
        except Exception:
            log.exception("trabajo falló para %s", telefono)
        finally:
            with _lock:
                _pendientes -= 1


def estado() -> dict:
    with _lock:
        return {
            "trabajadores": config.PROCESADORES_CONCURRENTES,
            "telefonos_activos": len(_activos),
            "mensajes_pendientes": _pendientes,
            "capacidad": config.COLA_MAX_MENSAJES,
        }


def cerrar() -> None:
    global _executor
    with _lock:
        executor, _executor = _executor, None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)
