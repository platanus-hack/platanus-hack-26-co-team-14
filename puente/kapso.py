"""
Cliente de Kapso: recibir el audio que entra, mandar texto, audio y documentos.

    enviar   POST {base}/meta/whatsapp/{version}/{phone_number_id}/messages
    subir    POST {base}/meta/whatsapp/{version}/{phone_number_id}/media
    auth     header  X-API-Key
"""

from __future__ import annotations

import hashlib
import hmac
import logging

import httpx

from . import config

log = logging.getLogger("kapso")

TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def _url(recurso: str) -> str:
    return (
        f"{config.KAPSO_API_BASE}/meta/whatsapp/{config.KAPSO_VERSION}"
        f"/{config.KAPSO_PHONE_NUMBER_ID}/{recurso}"
    )


def _headers(json: bool = True) -> dict:
    h = {"X-API-Key": config.KAPSO_API_KEY}
    if json:
        h["Content-Type"] = "application/json"
    return h


def _enviar(cuerpo: dict) -> dict:
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.post(_url("messages"), headers=_headers(), json=cuerpo)
    if r.status_code >= 400:
        log.error("envío %s → %s", r.status_code, r.text[:400])
        r.raise_for_status()
    respuesta = r.json()
    log.info(
        "envío confirmado tipo=%s destino=%s id=%s",
        cuerpo.get("type"),
        cuerpo.get("to"),
        ((respuesta.get("messages") or [{}])[0]).get("id"),
    )
    return respuesta


# ─── firma del webhook ────────────────────────────────────────────────────

def firma_valida(cuerpo_crudo: bytes, firma_recibida: str | None) -> bool:
    """HMAC-SHA256 hex del cuerpo con KAPSO_WEBHOOK_SECRET.

    Sin secreto configurado o con VERIFICAR_FIRMA=0 no bloquea: solo avisa.
    """
    if not config.VERIFICAR_FIRMA:
        return True
    if not config.KAPSO_WEBHOOK_SECRET:
        log.warning("VERIFICAR_FIRMA=1 sin KAPSO_WEBHOOK_SECRET; se deja pasar")
        return True
    if not firma_recibida:
        return False
    esperada = hmac.new(
        config.KAPSO_WEBHOOK_SECRET.encode(), cuerpo_crudo, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperada, firma_recibida.strip().lower())


# ─── entrantes ────────────────────────────────────────────────────────────

def extraer_mensajes(payload: dict) -> list[dict]:
    """Un mensaje suelto, o el sobre de lote que llega con debouncing:
    {"type": ..., "batch": true, "data": [...], "batch_info": {...}}
    """
    if payload.get("batch") and isinstance(payload.get("data"), list):
        return [d for d in payload["data"] if isinstance(d, dict)]
    return [payload]


def leer_mensaje(evento: dict) -> dict:
    """Normaliza un evento de Kapso v2 a lo que nos interesa."""
    msg = evento.get("message") or {}
    kap = msg.get("kapso") or {}
    conv = evento.get("conversation") or {}
    media = kap.get("media_data") or {}
    transcript = kap.get("transcript") or {}

    telefono = (
        conv.get("phone_number") or conv.get("wa_id")
        or msg.get("from") or evento.get("from")
    )

    return {
        "id": msg.get("id"),
        "tipo": msg.get("type"),
        "direccion": kap.get("direction", "inbound"),
        "telefono": telefono,
        "texto": (msg.get("text") or {}).get("body"),
        "media_url": kap.get("media_url") or media.get("url"),
        "media_tipo": media.get("content_type"),
        "media_nombre": media.get("filename"),
        "transcripcion_kapso": transcript.get("text"),
        "timestamp": msg.get("timestamp"),
    }


def descargar_media(url: str) -> bytes:
    """Descarga el audio entrante. La URL de Kapso requiere la API key."""
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as c:
        r = c.get(url, headers={"X-API-Key": config.KAPSO_API_KEY})
        r.raise_for_status()
        return r.content


# ─── salientes ────────────────────────────────────────────────────────────

def enviar_texto(telefono: str, texto: str) -> dict:
    return _enviar({
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": texto},
    })


def subir_media(contenido: bytes, nombre: str, content_type: str) -> str | None:
    """Sube un archivo y devuelve su media id. None si falla.

    Es la vía que funciona en serverless: no necesita disco ni URL pública.
    """
    archivos = {
        "file": (nombre, contenido, content_type),
        "messaging_product": (None, "whatsapp"),
        "type": (None, content_type),
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.post(_url("media"), headers=_headers(json=False), files=archivos)
        if r.status_code >= 400:
            log.error("subir_media %s → %s", r.status_code, r.text[:400])
            return None
        return r.json().get("id")
    except httpx.HTTPError as e:
        log.error("subir_media falló: %s", e)
        return None


def enviar_audio_por_id(telefono: str, media_id: str, nota_de_voz: bool = True) -> dict:
    return _enviar({
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "audio",
        "audio": {"id": media_id, "voice": nota_de_voz},
    })


def enviar_audio_por_link(telefono: str, link: str) -> dict:
    return _enviar({
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "audio",
        "audio": {"link": link},
    })


def enviar_documento_por_id(telefono: str, media_id: str, nombre: str,
                            descripcion: str = "") -> dict:
    """Manda un documento ya subido. Es la vía que sirve en serverless: el
    archivo vive en Kapso, no en un disco que desaparece al responder."""
    doc = {"id": media_id, "filename": nombre}
    if descripcion:
        doc["caption"] = descripcion
    return _enviar({
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "document",
        "document": doc,
    })


def enviar_documento(telefono: str, link: str, nombre: str,
                     descripcion: str = "") -> dict:
    doc = {"link": link, "filename": nombre}
    if descripcion:
        doc["caption"] = descripcion
    return _enviar({
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "document",
        "document": doc,
    })
