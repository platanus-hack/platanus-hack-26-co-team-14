"""
Dónde vive el caso entre un mensaje y el siguiente.

Un caso es lo que devuelve `core.estado.nuevo_caso()`. Aquí no se toca su
contenido: solo se guarda y se recupera por número de teléfono.

Dos capas:

    RAM     rápido, y suficiente mientras el proceso siga vivo.
    disco   JSON en una carpeta temporal, para que sobreviva a que el
            proceso no siga vivo.

Por qué el disco: en serverless cada petición puede caer en una instancia
distinta, y con memoria a secas la conversación se reinicia cada vez que la
usuaria manda un audio. El disco de Vercel es por instancia y efímero, así
que tampoco es garantía — pero una instancia caliente atiende varios mensajes
seguidos, y eso cubre una conversación normal.

Para producción esto se cambia por Redis o una tabla, y no hay que tocar nada
más: el resto del sistema solo llama a `obtener`, `guardar` y `borrar`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from threading import Lock

from core.estado import nuevo_caso

log = logging.getLogger("sesiones")

# Una conversación se apaga tras diez minutos sin mensajes. El valor puede
# ajustarse para pruebas, pero en producción el defecto protege los datos de
# salud y evita que un mensaje tardío reactive un formulario anterior.
TTL_SEGUNDOS = int(os.getenv("SESION_TTL_SEGUNDOS", "600"))

_MEMORIA: dict[str, dict] = {}
_LOCK = Lock()

EN_SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))

DIR_SESIONES = (
    Path(tempfile.gettempdir()) / "tutela_sesiones"
    if EN_SERVERLESS
    else Path(__file__).resolve().parent.parent / ".sesiones"
)

try:
    DIR_SESIONES.mkdir(parents=True, exist_ok=True)
    HAY_DISCO = True
except OSError as e:                      # sistema de archivos de solo lectura
    log.warning("sin disco para sesiones (%s); solo memoria", e)
    HAY_DISCO = False


def _archivo(clave: str) -> Path:
    """Un teléfono no es un nombre de archivo hasta que se limpia."""
    return DIR_SESIONES / f"{re.sub(r'[^0-9a-zA-Z]', '', clave)}.json"


def _leer_disco(clave: str) -> dict | None:
    if not HAY_DISCO:
        return None
    ruta = _archivo(clave)
    try:
        if not ruta.exists():
            return None
        if time.time() - ruta.stat().st_mtime > TTL_SEGUNDOS:
            ruta.unlink(missing_ok=True)
            return None
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("sesión ilegible en disco (%s): %s", clave, e)
        return None


def _escribir_disco(clave: str, caso: dict) -> None:
    if not HAY_DISCO:
        return
    try:
        _archivo(clave).write_text(
            json.dumps(caso, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except (OSError, TypeError) as e:
        log.warning("no pude guardar la sesión (%s): %s", clave, e)


def obtener(clave: str) -> dict:
    """El caso de esa persona. Si no hay ninguno, uno nuevo."""
    ahora = time.time()
    with _LOCK:
        caso = _MEMORIA.get(clave)
        if caso and ahora - float(caso.get("_ultima_actividad", 0)) > TTL_SEGUNDOS:
            _MEMORIA.pop(clave, None)
            caso = None
            log.info("sesión expirada por inactividad para %s", clave)

    if caso is None:
        caso = _leer_disco(clave)

    if caso and ahora - float(caso.get("_ultima_actividad", 0)) > TTL_SEGUNDOS:
        borrar(clave)
        caso = None

    if caso is None:
        caso = nuevo_caso(session_id=clave)
        caso["_ultima_actividad"] = ahora
        log.info("caso nuevo para %s", clave)

    return deepcopy(caso)


def guardar(clave: str, caso: dict) -> None:
    caso = deepcopy(caso)
    caso["_ultima_actividad"] = time.time()
    with _LOCK:
        _MEMORIA[clave] = caso
    _escribir_disco(clave, caso)


def borrar(clave: str) -> None:
    """Cierra el caso. Se llama cuando el documento ya salió: no guardamos
    casos individuales más de lo necesario (Ley 1581 de 2012, art. 5)."""
    with _LOCK:
        _MEMORIA.pop(clave, None)
    if HAY_DISCO:
        try:
            _archivo(clave).unlink(missing_ok=True)
        except OSError:
            pass


def activas() -> int:
    """Cuántas conversaciones hay abiertas en esta instancia. Para /salud."""
    ahora = time.time()
    with _LOCK:
        expiradas = [
            clave for clave, caso in _MEMORIA.items()
            if ahora - float(caso.get("_ultima_actividad", 0)) > TTL_SEGUNDOS
        ]
        for clave in expiradas:
            _MEMORIA.pop(clave, None)
        return len(_MEMORIA)
