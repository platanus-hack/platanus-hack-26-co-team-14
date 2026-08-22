"""
La ruta que ya está pegada en Kapso: `/webhooks/kapso`.

Antes aquí vivía un normalizador propio del payload. Ahora hay uno solo, el
del puente (`puente/kapso.py`), que conoce la forma real de los eventos v2 —
lotes con debouncing, `kapso.media_url`, transcripción propia, firma HMAC—.
Dos normalizadores del mismo JSON es un divergente esperando a pasar.

Así que esto es un alias: misma entrada, mismo manejador, otra URL. Sirve
para no tener que volver a tocar la configuración de Kapso.

La ruta canónica es `/webhooks/whatsapp`.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Header, Request

from puente.app import webhook

router = APIRouter()


@router.post("/webhooks/kapso")
async def webhook_kapso(
    request: Request,
    tareas: BackgroundTasks,
    x_webhook_event: str | None = Header(default=None),
    x_webhook_signature: str | None = Header(default=None),
    x_idempotency_key: str | None = Header(default=None),
):
    return await webhook(
        request,
        tareas,
        x_webhook_event=x_webhook_event,
        x_webhook_signature=x_webhook_signature,
        x_idempotency_key=x_idempotency_key,
    )
