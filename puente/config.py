"""Configuración del puente. Todo sale de variables de entorno (.env)."""

from __future__ import annotations

import hashlib
import os
import secrets

from dotenv import load_dotenv

# override=True a propósito: el .env manda sobre lo que ya haya en el entorno.
# Sin esto, una llave vieja exportada en el sistema le gana al .env en silencio
# y se depura un 401 que no existe. En Vercel no se sube .env (ver .vercelignore),
# así que allí siguen mandando las variables del proyecto.
load_dotenv(override=True)


def _v(nombre: str, defecto: str = "") -> str:
    return os.getenv(nombre, defecto).strip().strip('"').strip("'")


# ─── Kapso ────────────────────────────────────────────────────────────────
KAPSO_API_KEY = _v("KAPSO_API_KEY")
KAPSO_PHONE_NUMBER_ID = _v("KAPSO_PHONE_NUMBER_ID")
KAPSO_WEBHOOK_SECRET = _v("KAPSO_WEBHOOK_SECRET")
KAPSO_API_BASE = _v("KAPSO_API_BASE", "https://api.kapso.ai")
KAPSO_VERSION = _v("KAPSO_VERSION", "v24.0")

# ─── ElevenLabs ───────────────────────────────────────────────────────────
ELEVENLABS_API_KEY = _v("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = _v("ELEVENLABS_VOICE_ID")
ELEVENLABS_STT_MODEL = _v("ELEVENLABS_STT_MODEL", "scribe_v1")
ELEVENLABS_STT_LANGUAGE = _v("ELEVENLABS_STT_LANGUAGE", "spa")
ELEVENLABS_TTS_MODEL = _v("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"

# Ajustes de la voz. Estabilidad alta = más monótona pero más predecible;
# para leerle datos legales a alguien mayor, conviene alta.
TTS_ESTABILIDAD = float(_v("TTS_ESTABILIDAD", "0.6") or "0.6")
TTS_SIMILITUD = float(_v("TTS_SIMILITUD", "0.8") or "0.8")
TTS_VELOCIDAD = float(_v("TTS_VELOCIDAD", "0.9") or "0.9")

# ─── Backend del equipo ───────────────────────────────────────────────────
# A dónde manda el puente lo que dijo la usuaria. Si está vacío, el puente
# responde en modo eco (útil para probar sin backend).
BACKEND_URL = _v("BACKEND_URL").rstrip("/")
BACKEND_TOKEN = _v("BACKEND_TOKEN")
BACKEND_TIMEOUT = float(_v("BACKEND_TIMEOUT", "30") or "30")

# ─── Seguridad de la API del puente ───────────────────────────────────────
# El backend usa este token para llamar a /api/*.
def _api_token() -> str:
    """Token de la API. Si no se define, se DERIVA de las llaves.

    No puede ser aleatorio: en serverless la fase 1 y la fase 2 corren en
    instancias distintas, y con un token al vuelo cada una tendría el suyo,
    así que la auto-invocación se rechazaría a sí misma con un 401.
    """
    if fijado := _v("API_TOKEN"):
        return fijado
    semilla = (_v("KAPSO_API_KEY") + _v("ELEVENLABS_API_KEY")).encode()
    if semilla.strip():
        return hashlib.sha256(semilla + b"puente-tutela-voz").hexdigest()[:32]
    return secrets.token_urlsafe(24)


API_TOKEN = _api_token()
API_TOKEN_DERIVADO = not _v("API_TOKEN")

VERIFICAR_FIRMA = _v("VERIFICAR_FIRMA", "0") == "1"
UMBRAL_CONFIANZA_STT = float(_v("UMBRAL_CONFIANZA_STT", "0.75") or "0.75")

# ─── Servidor ─────────────────────────────────────────────────────────────
PORT = int(_v("PORT", "8000") or "8000")
EN_VERCEL = bool(_v("VERCEL") or _v("VERCEL_ENV"))


def _ruta(nombre: str, defecto: str) -> str:
    """Git Bash convierte "/x" en "C:/Program Files/Git/x" al exportar."""
    bruto = _v(nombre, defecto)
    if ":" in bruto or "\\" in bruto or " " in bruto:
        bruto = defecto
    return "/" + bruto.strip("/")


WEBHOOK_PATH = _ruta("WEBHOOK_PATH", "/webhooks/whatsapp")
TAREA_PATH = "/tareas/procesar"


def _base_publica() -> tuple[str, str]:
    """URL pública del servicio y de dónde salió."""
    if manual := _v("PUBLIC_BASE_URL"):
        return manual.rstrip("/"), "PUBLIC_BASE_URL"
    for var in ("VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_URL"):
        if host := _v(var):
            host = host if host.startswith("http") else f"https://{host}"
            return host.rstrip("/"), f"{var} (Vercel)"
    if render := _v("RENDER_EXTERNAL_URL"):
        return render.rstrip("/"), "RENDER_EXTERNAL_URL (Render)"
    if railway := _v("RAILWAY_PUBLIC_DOMAIN"):
        return f"https://{railway}", "RAILWAY_PUBLIC_DOMAIN"
    return "", "(sin definir)"


PUBLIC_BASE_URL, ORIGEN_BASE_URL = _base_publica()


def _modo_proceso() -> str:
    """Cómo se hace el trabajo pesado sin pasarse de los 10 s de Kapso.

    "http"       el webhook se auto-invoca en una segunda petición y responde
                 al instante. Es lo único que funciona en serverless (Vercel),
                 donde el proceso muere en cuanto responde.
    "background" el webhook encola en el mismo proceso. Sirve donde el
                 servidor es persistente (local, Render).
    """
    if forzado := _v("MODO_PROCESO"):
        return forzado
    if EN_VERCEL:
        return "http"
    return "background"


MODO_PROCESO = _modo_proceso()

# En serverless no hay disco: el audio se sube a Kapso y se manda por media_id.
GUARDAR_MEDIA_EN_DISCO = not EN_VERCEL


def url_webhook() -> str:
    return f"{PUBLIC_BASE_URL}{WEBHOOK_PATH}" if PUBLIC_BASE_URL else ""


def faltantes() -> list[str]:
    return [
        n for n, v in {
            "KAPSO_API_KEY": KAPSO_API_KEY,
            "KAPSO_PHONE_NUMBER_ID": KAPSO_PHONE_NUMBER_ID,
            "ELEVENLABS_API_KEY": ELEVENLABS_API_KEY,
            "ELEVENLABS_VOICE_ID": ELEVENLABS_VOICE_ID,
        }.items() if not v
    ]
