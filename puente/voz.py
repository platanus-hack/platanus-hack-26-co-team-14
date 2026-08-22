"""
ElevenLabs: STT de entrada (Scribe) y TTS de salida.

    STT  POST https://api.elevenlabs.io/v1/speech-to-text        (multipart)
    TTS  POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
    auth header  xi-api-key

Formatos: ElevenLabs entrega mp3 / opus / pcm / wav. WhatsApp solo acepta como
NOTA DE VOZ un .ogg con codec OPUS. Pedimos opus_48000_64 y comprobamos los
magic bytes: si empieza por "OggS" sirve como nota de voz; si no, se manda
como mp3 (se reproduce igual, sin la onda).
"""

from __future__ import annotations

import logging
import math

import httpx

from . import config

log = logging.getLogger("voz")

TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# Límite por petición de TTS. Textos más largos se parten en frases.
MAX_CARACTERES = 2500


def _headers() -> dict:
    return {"xi-api-key": config.ELEVENLABS_API_KEY}


# ─── STT ──────────────────────────────────────────────────────────────────

def _confianza(datos: dict) -> float:
    """Confianza global 0–1 a partir de los logprob por palabra.

    logprob ∈ (-inf, 0]; exp(logprob) es la probabilidad. Se promedia sobre
    las palabras reales. Sin logprobs, se cae a language_probability.
    """
    palabras = [
        p for p in (datos.get("words") or [])
        if p.get("type") == "word" and isinstance(p.get("logprob"), (int, float))
    ]
    if palabras:
        media = sum(p["logprob"] for p in palabras) / len(palabras)
        return round(min(1.0, math.exp(media)), 4)
    lp = datos.get("language_probability")
    return round(float(lp), 4) if isinstance(lp, (int, float)) else 0.0


def transcribir(audio: bytes, nombre: str = "audio.ogg",
                content_type: str = "audio/ogg") -> dict:
    """Audio → {texto, duracion, confianza, idioma}."""
    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("Falta ELEVENLABS_API_KEY")

    datos = {
        "model_id": config.ELEVENLABS_STT_MODEL,
        "timestamps_granularity": "word",
    }
    if config.ELEVENLABS_STT_LANGUAGE:
        datos["language_code"] = config.ELEVENLABS_STT_LANGUAGE

    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.post(
            f"{config.ELEVENLABS_API_BASE}/speech-to-text",
            headers=_headers(), data=datos,
            files={"file": (nombre, audio, content_type)},
        )
        if r.status_code >= 400:
            log.error("STT %s → %s", r.status_code, r.text[:400])
        r.raise_for_status()
        cuerpo = r.json()

    palabras = cuerpo.get("words") or []
    duracion = max((p.get("end") or 0) for p in palabras) if palabras else 0.0

    return {
        "texto": (cuerpo.get("text") or "").strip(),
        "duracion": round(float(duracion), 2),
        "confianza": _confianza(cuerpo),
        "idioma": cuerpo.get("language_code"),
    }


# ─── TTS ──────────────────────────────────────────────────────────────────

def _recortar(texto: str) -> str:
    """Recorta por frase, no a la mitad de una palabra."""
    texto = texto.strip()
    if len(texto) <= MAX_CARACTERES:
        return texto
    corte = texto[:MAX_CARACTERES]
    for sep in (". ", "? ", "! ", ", ", " "):
        if (i := corte.rfind(sep)) > MAX_CARACTERES * 0.6:
            return corte[: i + 1].strip()
    return corte


def sintetizar(texto: str, voice_id: str | None = None) -> tuple[bytes, str, str]:
    """Texto → (bytes, content_type, extensión).

    Intenta OGG/Opus para poder mandarlo como nota de voz. Si ElevenLabs no
    devuelve contenedor OGG, cae a mp3.
    """
    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("Falta ELEVENLABS_API_KEY")
    voz_id = voice_id or config.ELEVENLABS_VOICE_ID
    if not voz_id:
        raise RuntimeError("Falta ELEVENLABS_VOICE_ID "
                           "(míralas con: python -m puente.probar --voces)")

    cuerpo = {
        "text": _recortar(texto),
        "model_id": config.ELEVENLABS_TTS_MODEL,
        "voice_settings": {
            "stability": config.TTS_ESTABILIDAD,
            "similarity_boost": config.TTS_SIMILITUD,
            "speed": config.TTS_VELOCIDAD,
        },
    }
    url = f"{config.ELEVENLABS_API_BASE}/text-to-speech/{voz_id}"

    for formato in ("opus_48000_64", "mp3_44100_128"):
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.post(url, headers={**_headers(), "Content-Type": "application/json"},
                       params={"output_format": formato}, json=cuerpo)
        if r.status_code >= 400:
            log.warning("TTS %s con %s → %s", r.status_code, formato, r.text[:300])
            continue

        audio = r.content
        if formato.startswith("opus"):
            if audio[:4] == b"OggS":          # contenedor OGG → nota de voz
                return audio, "audio/ogg", "ogg"
            log.info("opus sin contenedor OGG; se usa mp3")
            continue
        return audio, "audio/mpeg", "mp3"

    raise RuntimeError("ElevenLabs no devolvió audio en ningún formato")


def listar_voces() -> list[dict]:
    """Voces de la cuenta: [{voice_id, nombre, etiquetas}]."""
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{config.ELEVENLABS_API_BASE}/voices", headers=_headers())
    r.raise_for_status()
    return [
        {
            "voice_id": v.get("voice_id"),
            "nombre": v.get("name"),
            "etiquetas": v.get("labels") or {},
        }
        for v in r.json().get("voices", [])
    ]
