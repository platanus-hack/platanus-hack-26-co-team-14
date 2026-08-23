"""
Cliente del backend del equipo.

El puente NO decide nada del negocio: transcribe, se lo manda al backend, y
hace lo que el backend le diga.

Hay tres modos, y se escogen solos en este orden:

1. BACKEND_URL definido  →  se llama por HTTP.

       PUENTE  ──POST {BACKEND_URL}/mensaje──>  BACKEND
       PUENTE  <────── {"responder": [...]} ──  BACKEND

2. Sin BACKEND_URL pero con un manejador registrado con `registrar_local()`
   →  se llama en el mismo proceso, sin red. Es lo que hace este repo:
   `canal/cerebro.py` implementa el mismo contrato y lo registra al arrancar.
   Sin salto HTTP no hay token que cuadrar ni latencia que pagar.

3. Ninguno de los dos  →  eco, para probar el canal a solas.

El contrato (la forma del mensaje y de `responder`) es el mismo en los tres
casos y está descrito en puente/README.md.
"""

from __future__ import annotations

import logging

import httpx

from . import config

log = logging.getLogger("backend")

# Manejador en proceso. Lo registra el entrypoint (app.py) para que el puente
# no tenga que importar el cerebro: el puente sigue sin saber nada del negocio.
_local = None
_control_datos = None


def registrar_local(manejador, control_datos=None) -> None:
    """Conecta un backend que vive en este mismo proceso.

    `manejador(mensaje: dict) -> list[dict]` recibe el mismo contrato que
    recibiría por HTTP y devuelve la misma lista de acciones.
    """
    global _local, _control_datos
    _local = manejador
    _control_datos = control_datos
    log.info("backend en proceso registrado: %s", getattr(manejador, "__module__", "?"))


def permite_procesar_datos(telefono: str) -> bool:
    """Evita descargar/transcribir audio antes del consentimiento."""
    if config.BACKEND_URL or _control_datos is None:
        return True
    return bool(_control_datos(telefono))


def hay_backend() -> bool:
    return bool(config.BACKEND_URL) or _local is not None


def modo() -> str:
    if config.BACKEND_URL:
        return "http"
    if _local is not None:
        return "en_proceso"
    return "eco"


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if config.BACKEND_TOKEN:
        h["Authorization"] = f"Bearer {config.BACKEND_TOKEN}"
    return h


def procesar(mensaje: dict) -> list[dict]:
    """Manda el mensaje al backend y devuelve la lista de acciones.

    `mensaje` es el contrato de entrada; la respuesta esperada es
    {"responder": [ {tipo, ...}, ... ]}.

    Si el backend falla o no está configurado, se cae a eco: el puente sigue
    respondiendo algo en vez de dejar a la usuaria en silencio.
    """
    if not config.BACKEND_URL:
        if _local is None:
            return _eco(mensaje)
        try:
            acciones = _local(mensaje)
        except Exception:
            log.exception("el backend en proceso falló")
            return _fallo()
        return _validar(acciones)

    url = f"{config.BACKEND_URL}/mensaje"
    try:
        with httpx.Client(timeout=config.BACKEND_TIMEOUT) as c:
            r = c.post(url, headers=_headers(), json=mensaje)
        if r.status_code >= 400:
            log.error("backend %s → %s", r.status_code, r.text[:400])
            return _fallo()
        datos = r.json()
    except Exception as e:
        log.error("backend inalcanzable (%s): %s", url, e)
        return _fallo()

    return _validar(datos.get("responder"))


def _validar(acciones) -> list[dict]:
    """Deja pasar solo acciones con forma de acción."""
    if not isinstance(acciones, list):
        log.error("el backend no devolvió 'responder' como lista: %s", str(acciones)[:300])
        return _fallo()
    return [a for a in acciones if isinstance(a, dict) and a.get("tipo")]


def _eco(mensaje: dict) -> list[dict]:
    """Modo sin backend: repite lo que entendió, en texto y en voz."""
    texto = (mensaje.get("texto") or "").strip()
    tr = mensaje.get("transcripcion") or {}

    if not texto:
        return [{"tipo": "audio",
                 "texto": "No logré entender el audio. ¿Me lo puede repetir más despacio?"}]

    conf = tr.get("confianza")
    pie = f"\n\n_confianza {conf:.0%}_" if isinstance(conf, (int, float)) else ""
    return [
        {"tipo": "texto", "texto": f"Esto fue lo que entendí:\n\n{texto}{pie}"},
        {"tipo": "audio",
         "texto": f"Le repito lo que entendí, y usted me dice si está bien. {texto}"},
    ]


def _fallo() -> list[dict]:
    return [{"tipo": "texto",
             "texto": "Estamos con una falla técnica. Vuelva a intentarlo en un momento."}]
