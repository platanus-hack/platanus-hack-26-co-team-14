"""Constancias mínimas y verificables de autorización por WhatsApp."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from puente import config

log = logging.getLogger("consentimientos")
VERSION_AVISO = "2026-08-23-v1"
DIR_CONSTANCIAS = Path(tempfile.gettempdir()) / "temis_consentimientos"


def _id_titular(telefono: str) -> str:
    secreto = (config.API_TOKEN or "temis-consentimiento").encode()
    return hmac.new(secreto, telefono.encode(), hashlib.sha256).hexdigest()


def registrar(telefono: str, mensaje_id: str | None, respuesta: str) -> dict:
    """Conserva prueba de la autorización sin escribir el teléfono en claro."""
    constancia = {
        "titular_hash": _id_titular(telefono),
        "mensaje_id": mensaje_id,
        "fecha": datetime.now(timezone.utc).isoformat(),
        "canal": "whatsapp",
        "version_aviso": VERSION_AVISO,
        "respuesta": respuesta,
    }
    try:
        DIR_CONSTANCIAS.mkdir(parents=True, exist_ok=True)
        nombre = mensaje_id or hashlib.sha256(
            json.dumps(constancia, sort_keys=True).encode()).hexdigest()
        nombre = "".join(c for c in nombre if c.isalnum() or c in "-_")
        (DIR_CONSTANCIAS / f"{nombre}.json").write_text(
            json.dumps(constancia, ensure_ascii=False), encoding="utf-8")
    except OSError:
        log.exception("no fue posible persistir la constancia de consentimiento")
    return constancia
