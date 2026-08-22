"""
TEMIS — punto de entrada único.

Una sola aplicación FastAPI. El puente trae sus endpoints ya montados y aquí
se le enchufa el cerebro, que es el backend de este mismo repo.

    WhatsApp ─Kapso─> /webhooks/whatsapp ─┐
                                          ├─> canal.cerebro ─> core ─> juridico
    otro backend ────> POST /mensaje ─────┘

Por qué el cerebro va en el mismo proceso y no detrás de una URL: el puente
sabe hablar con un backend por HTTP (BACKEND_URL) y lo sigue sabiendo. Pero
aquí los dos viven en el mismo despliegue, y hacer que una función serverless
se llame a sí misma por internet para preguntarse qué contestar cuesta una
petición, un token y un timeout, y no compra nada.

Si algún día el backend se va a otro sitio, se define BACKEND_URL y este
archivo no cambia: `cerebro.conectar()` se aparta solo.

ENDPOINTS
    POST  /webhooks/whatsapp   entrada de Kapso (canónica)
    POST  /webhooks/kapso      la misma, con el nombre viejo
    POST  /mensaje             el contrato del backend, por HTTP
    GET   /salud               diagnóstico completo
    GET   /health              lo mismo, para healthchecks
    POST  /api/enviar          mandar un mensaje cuando se quiera
    POST  /api/voz             texto → audio
    POST  /api/transcribir     audio → texto
    GET   /api/voces           voces disponibles
"""

from __future__ import annotations

import logging
import os

from fastapi import Header, Request
from fastapi.responses import JSONResponse

from puente import config
from puente.app import app          # trae el puente entero, ya montado

from canal import cerebro
from canal.kapso import router as kapso_router
from canal.sesiones import activas
from juridico.render import PLANTILLAS

PLANTILLAS_DISPONIBLES = [t for t, ruta in PLANTILLAS.items() if ruta.exists()]

log = logging.getLogger("temis")

app.title = "TEMIS — Tutela Voz"

# El puente empieza a usar el cerebro de este repo. A partir de aquí, todo lo
# que entre por WhatsApp termina en core/ y juridico/.
cerebro.conectar()

# `/webhooks/kapso`, por si Kapso ya apunta ahí.
app.include_router(kapso_router)


# ============================================================
# EL CONTRATO, POR HTTP
# ============================================================

@app.post("/mensaje")
async def mensaje(request: Request,
                  authorization: str | None = Header(default=None)):
    """El mismo contrato que usa el puente en proceso, expuesto por HTTP.

    Sirve para dos cosas: probar el cerebro sin WhatsApp, y permitir que otro
    despliegue del puente apunte aquí con BACKEND_URL.
    """
    if config.BACKEND_TOKEN:
        recibido = (authorization or "").removeprefix("Bearer ").strip()
        if recibido != config.BACKEND_TOKEN:
            return JSONResponse({"error": "no autorizado"}, status_code=401)

    try:
        cuerpo = await request.json()
    except Exception:
        return JSONResponse({"error": "cuerpo no json"}, status_code=400)

    if not cuerpo.get("telefono"):
        return JSONResponse({"error": "falta telefono"}, status_code=400)

    return {"responder": cerebro.responder(cuerpo)}


# ============================================================
# SALUD
# ============================================================

@app.get("/health")
def health():
    """Healthcheck corto. El diagnóstico del canal está en /salud."""
    from puente import backend

    return {
        "ok": True,
        "servicio": "temis",
        "backend": backend.modo(),
        "extraccion_lista": bool(os.getenv("ANTHROPIC_API_KEY")),
        "conversaciones_abiertas": activas(),
        "plantillas": sorted(PLANTILLAS_DISPONIBLES),
    }
