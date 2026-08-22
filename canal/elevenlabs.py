"""
Adaptador de transcripción.

Este módulo aísla ElevenLabs del resto del sistema.

Kapso -> audio -> ElevenLabs -> texto
"""

from typing import Optional


def transcribir_evento_kapso(
    evento: dict,
) -> Optional[str]:
    """
    Esta función debe conectarse con la implementación
    de ElevenLabs que ya tengas funcionando.

    Por ahora intenta reutilizar una transcripción
    que ya venga incluida en el evento.
    """

    mensaje = evento.get(
        "mensaje",
        {},
    )

    # Si el webhook ya trae la transcripción
    transcripcion = (
        mensaje.get("transcription")
        or mensaje.get("transcript")
        or evento.get("transcription")
        or evento.get("transcript")
    )

    if isinstance(
        transcripcion,
        str,
    ) and transcripcion.strip():

        return transcripcion.strip()

    # Todavía no inventamos cómo descargar el media
    # hasta ver el payload real de Kapso.
    raise RuntimeError(
        "El evento contiene audio pero no trae una "
        "transcripción. Falta conectar aquí el media "
        "de Kapso con la implementación existente "
        "de ElevenLabs."
    )