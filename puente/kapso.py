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
import re

import httpx

from . import config

log = logging.getLogger("kapso")

TIMEOUT = httpx.Timeout(60.0, connect=10.0)

_CLAVES_TELEFONO = {
    "from", "wa_id", "phone", "phone_number", "sender_phone",
    "sender_phone_number", "contact_phone", "contact_phone_number",
    "customer_phone", "customer_phone_number", "user_phone_number",
    # No incluimos phone_number_id ni los business_scoped_user_id: identifican
    # al negocio o a la persona dentro de Meta, pero no son números marcables.
}


def _es_numero_whatsapp(valor) -> bool:
    if not isinstance(valor, (str, int)):
        return False
    candidato = str(valor).strip()
    return bool(re.fullmatch(r"\+?[0-9][0-9 .()-]{6,24}", candidato))


def _buscar_telefono(objeto) -> str | None:
    """Encuentra el número de la persona sin confundirlo con phone_number_id."""
    if isinstance(objeto, dict):
        for clave, valor in objeto.items():
            if clave.lower() in _CLAVES_TELEFONO and _es_numero_whatsapp(valor):
                candidato = str(valor).strip()
                return candidato
        for valor in objeto.values():
            if encontrado := _buscar_telefono(valor):
                return encontrado
    elif isinstance(objeto, list):
        for valor in objeto:
            if encontrado := _buscar_telefono(valor):
                return encontrado
    return None


def _destinatario(*candidatos) -> str | None:
    """Devuelve solo identificadores escalares utilizables por Meta/Kapso."""
    for valor in candidatos:
        if not _es_numero_whatsapp(valor):
            continue
        candidato = str(valor).strip()
        return candidato
    return None


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
    # Algunos webhooks sin buffering conservan el sobre {event, data}.
    if isinstance(payload.get("data"), dict) and payload["data"].get("message"):
        return [payload["data"]]
    return [payload]


def leer_mensaje(evento: dict) -> dict:
    """Normaliza un evento de Kapso v2 a lo que nos interesa."""
    msg = evento.get("message") or {}
    kap = msg.get("kapso") or {}
    conv = evento.get("conversation") or {}
    media = kap.get("media_data") or {}
    transcript = kap.get("transcript") or {}
    interactive = msg.get("interactive") or {}
    button_reply = interactive.get("button_reply") or {}
    list_reply = interactive.get("list_reply") or {}
    kap_content = kap.get("content") if isinstance(kap.get("content"), dict) else {}
    boton_id = (
        button_reply.get("id") or list_reply.get("id")
        or msg.get("reply_option_id") or kap.get("reply_option_id")
        or kap_content.get("reply_option_id")
    )
    boton_titulo = (
        button_reply.get("title") or list_reply.get("title")
        or msg.get("reply_option_title") or kap.get("reply_option_title")
        or kap_content.get("reply_option_title")
    )

    telefono = _destinatario(
        # En payload v2 el número de la persona también viene dentro de
        # message.kapso.phone_number. Es distinto de phone_number_id, que
        # identifica el número de WhatsApp Business y no es el destinatario.
        kap.get("phone_number"), conv.get("phone_number"), conv.get("wa_id"),
        msg.get("from"), evento.get("from"),
        _buscar_telefono(evento),
    )

    return {
        "id": msg.get("id"),
        "tipo": msg.get("type") or msg.get("message_type"),
        "direccion": kap.get("direction") or msg.get("direction") or "inbound",
        "telefono": telefono,
        "conversation_id": conv.get("id") or kap.get("whatsapp_conversation_id"),
        "identidad_usuario": (
            msg.get("from_user_id") or conv.get("business_scoped_user_id")
            or msg.get("username") or conv.get("username")
        ),
        "texto": ((msg.get("text") or {}).get("body") or boton_titulo
                  or boton_id or (msg.get("content") if isinstance(msg.get("content"), str) else None)),
        "boton_id": boton_id,
        "boton_titulo": boton_titulo,
        "media_url": kap.get("media_url") or media.get("url"),
        "media_tipo": media.get("content_type"),
        "media_nombre": media.get("filename"),
        "transcripcion_kapso": transcript.get("text"),
        "timestamp": msg.get("timestamp"),
        # Solo nombres de campos, nunca contenido sensible. Sirve para ajustar
        # variantes nuevas del payload desde los logs de producción.
        "estructura": {
            "evento": sorted(evento.keys()),
            "mensaje": sorted(msg.keys()),
            "kapso": sorted(kap.keys()),
            "conversacion": sorted(conv.keys()),
        },
    }


def resolver_telefono_conversacion(conversation_id: str) -> str | None:
    """Consulta Kapso cuando el webhook trae BSUID pero omite el teléfono."""
    url = (
        f"{config.KAPSO_API_BASE}/meta/whatsapp/{config.KAPSO_VERSION}/"
        f"{config.KAPSO_PHONE_NUMBER_ID}/conversations/{conversation_id}"
    )
    with httpx.Client(timeout=TIMEOUT) as cliente:
        respuesta = cliente.get(url, headers=_headers(json=False))
    respuesta.raise_for_status()
    datos = respuesta.json()
    if isinstance(datos.get("data"), dict):
        datos = datos["data"]
    telefono = datos.get("phone_number") or datos.get("wa_id")
    return str(telefono).strip() if _es_numero_whatsapp(telefono) else None


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


def enviar_botones(telefono: str, texto: str, botones: list[dict],
                   encabezado: str | None = None,
                   pie: str | None = None) -> dict:
    """Envía botones de respuesta rápida dentro de la ventana de conversación."""
    # Meta limita el cuerpo interactivo. Si el aviso legal es largo, se manda
    # primero completo y los botones quedan en un segundo mensaje corto.
    if len(texto) > 1000:
        enviar_texto(telefono, texto)
        texto = "Después de leer el aviso, ¿autoriza el tratamiento de sus datos?"
    interactive = {
        "type": "button",
        "body": {"text": texto},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {"id": str(b["id"]), "title": str(b["titulo"])[:20]},
                }
                for b in botones[:3]
            ]
        },
    }
    if encabezado:
        interactive["header"] = {"type": "text", "text": encabezado}
    if pie:
        interactive["footer"] = {"text": pie}
    return _enviar({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefono,
        "type": "interactive",
        "interactive": interactive,
    })


def marcar_leido_escribiendo(message_id: str) -> dict:
    """Marca el mensaje como leído y muestra «escribiendo…» en WhatsApp.

    Meta lo retira al enviar la respuesta o después de unos 25 segundos.
    """
    return _enviar({
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
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
