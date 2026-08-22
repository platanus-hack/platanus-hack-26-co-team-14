import json
import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Request,
)

from canal.orquestador import (
    procesar_turno_core,
    construir_respuesta_final,
)


router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/webhooks/kapso")
async def webhook_kapso(
    request: Request,
    background_tasks: BackgroundTasks,
):
    payload = await request.json()

    # IMPORTANTE PARA LA PRIMERA PRUEBA:
    # queremos ver exactamente qué manda Kapso.
    logger.info(
        "KAPSO WEBHOOK:\n%s",
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
    )

    background_tasks.add_task(
        procesar_evento_kapso,
        payload,
    )

    # ACK inmediato
    return {
        "ok": True
    }


def procesar_evento_kapso(
    payload: dict,
):
    try:
        evento = normalizar_evento(
            payload
        )

        if not evento:
            logger.info(
                "Evento Kapso ignorado: no contiene mensaje compatible."
            )
            return

        logger.info(
            "EVENTO NORMALIZADO:\n%s",
            json.dumps(
                evento,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

        usuario_id = evento[
            "usuario_id"
        ]

        texto = obtener_texto(
            evento
        )

        if not texto:
            logger.warning(
                "No se obtuvo texto para usuario %s",
                usuario_id,
            )

            # Durante la primera prueba no mandamos
            # nada todavía hasta tener listo el cliente
            # de envío Kapso.
            return

        logger.info(
            "TEXTO RECIBIDO [%s]: %s",
            usuario_id,
            texto,
        )

        resultado_core = procesar_turno_core(
            usuario_id,
            texto,
        )

        logger.info(
            "RESULTADO CORE:\n%s",
            json.dumps(
                resultado_core,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

        respuesta = construir_respuesta_final(
            usuario_id,
            resultado_core,
        )

        logger.info(
            "RESPUESTA A ENVIAR:\n%s",
            json.dumps(
                respuesta,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

        # Lo activamos cuando tengamos confirmado
        # el endpoint real de envío de Kapso.
        #
        # enviar_respuesta(
        #     usuario_id,
        #     respuesta,
        # )

    except Exception:
        logger.exception(
            "Error procesando webhook Kapso"
        )


def normalizar_evento(
    payload: dict,
):
    """
    Convierte el JSON externo a nuestro formato interno.

    Esta función es provisional hasta ver
    el payload real de Kapso.
    """

    mensaje = (
        payload.get("message")
        or payload.get(
            "data",
            {}
        ).get("message")
    )

    if not mensaje:
        return None

    usuario_id = (
        mensaje.get("from")
        or mensaje.get("wa_id")
        or mensaje.get("phone")
    )

    if not usuario_id:
        return None

    tipo = (
        mensaje.get("type")
        or "unknown"
    )

    return {
        "usuario_id":
            str(usuario_id),

        "tipo":
            str(tipo),

        "mensaje":
            mensaje,

        "raw":
            payload,
    }


def obtener_texto(
    evento: dict,
):
    mensaje = evento[
        "mensaje"
    ]

    tipo = evento[
        "tipo"
    ].lower()

    # ========================================================
    # 1. TRANSCRIPCIÓN YA DISPONIBLE
    # ========================================================

    transcripcion = (
        mensaje.get("transcription")
        or mensaje.get("transcript")
        or evento.get("transcription")
        or evento.get("transcript")
    )

    if (
        isinstance(
            transcripcion,
            str,
        )
        and transcripcion.strip()
    ):
        return transcripcion.strip()

    # ========================================================
    # 2. TEXTO
    # ========================================================

    if tipo == "text":

        texto = mensaje.get(
            "text"
        )

        if isinstance(
            texto,
            dict,
        ):
            texto = texto.get(
                "body"
            )

        if (
            isinstance(
                texto,
                str,
            )
            and texto.strip()
        ):
            return texto.strip()

        return None

    # ========================================================
    # 3. AUDIO
    # ========================================================

    if tipo in {
        "audio",
        "voice",
    }:
        return transcribir_audio(
            evento
        )

    return None

def transcribir_audio(
    evento: dict,
):
    """
    Usa el adaptador que ya tengas conectado
    con ElevenLabs.
    """

    from canal.elevenlabs import (
        transcribir_evento_kapso,
    )

    texto = transcribir_evento_kapso(
        evento
    )

    if not texto:
        return None

    return str(texto).strip()