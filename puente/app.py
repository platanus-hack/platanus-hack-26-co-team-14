"""
PUENTE — WhatsApp (Kapso) ↔ voz (ElevenLabs) ↔ backend del equipo.

El puente no decide nada del negocio. Recibe, transcribe, se lo pasa al
backend, y hace lo que el backend le diga.

    usuaria ──audio──> Kapso ──webhook──> PUENTE ──POST /mensaje──> BACKEND
    usuaria <──audio── Kapso <──envío──── PUENTE <──{responder}──── BACKEND

ENDPOINTS
    POST  /webhooks/whatsapp   entrada de Kapso (fase 1: responde al instante)
    POST  /tareas/procesar     trabajo pesado  (fase 2: interno)
    POST  /api/enviar          el backend manda un mensaje cuando quiera
    POST  /api/voz             texto → audio
    POST  /api/transcribir     audio → texto
    GET   /api/voces           voces disponibles
    GET   /salud               diagnóstico
    GET   /media/{nombre}      sirve audio generado (solo fuera de serverless)

POR QUÉ DOS FASES
    Kapso exige 200 OK en menos de 10 s y reintenta a los 10 s, 40 s y 90 s.
    STT + backend + TTS tardan más. En un servidor persistente basta con
    encolar; en serverless (Vercel) el proceso muere al responder, así que el
    webhook se auto-invoca por HTTP y devuelve 200 de inmediato.
    Lo elige config.MODO_PROCESO: "http" (Vercel) o "background" (Render/local).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response

from . import backend, config, kapso, voz

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("puente")

@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    al_arrancar()
    yield


app = FastAPI(title="Puente Tutela Voz", version="1.0", lifespan=ciclo_de_vida)

# En serverless el disco es efímero: solo /tmp y no sobrevive. El audio se
# manda subiéndolo a Kapso (media_id), que no necesita disco.
DIR_MEDIA = Path("/tmp/puente_media") if config.EN_VERCEL \
    else Path(__file__).parent / "_media"
DIR_DOCS = Path("/tmp/puente_documentos") if config.EN_VERCEL \
    else Path(__file__).parent / "_documentos"
try:
    DIR_MEDIA.mkdir(parents=True, exist_ok=True)
    DIR_DOCS.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# Idempotencia: Kapso reintenta. En serverless la memoria no persiste entre
# invocaciones, así que esto solo protege dentro de una misma instancia.
_vistos: dict[str, float] = {}
VENTANA_IDEMPOTENCIA = 600


def _ya_procesado(clave: str | None) -> bool:
    if not clave:
        return False
    ahora = time.time()
    for k, t in list(_vistos.items()):
        if ahora - t > VENTANA_IDEMPOTENCIA:
            _vistos.pop(k, None)
    if clave in _vistos:
        return True
    _vistos[clave] = ahora
    return False


def _autorizado(cabecera: str | None) -> bool:
    if not cabecera:
        return False
    token = cabecera.removeprefix("Bearer ").strip()
    return token == config.API_TOKEN


# ═══════════════════════════════════════════════════════════ diagnóstico ═══

@app.get("/")
def raiz():
    return {"servicio": "puente-tutela-voz", "salud": "/salud", "docs": "/docs"}


@app.get("/salud")
def salud():
    return {
        "pegar_en_kapso": config.url_webhook() or None,
        "url_publica": config.PUBLIC_BASE_URL or None,
        "origen_url_publica": config.ORIGEN_BASE_URL,
        "ruta_webhook": config.WEBHOOK_PATH,
        "modo_proceso": config.MODO_PROCESO,
        "en_vercel": config.EN_VERCEL,
        "backend_configurado": backend.hay_backend(),
        "backend_modo": backend.modo(),
        "backend_url": config.BACKEND_URL or None,
        "faltan_en_env": config.faltantes(),
        "verificar_firma": config.VERIFICAR_FIRMA,
        "voz_configurada": bool(config.ELEVENLABS_VOICE_ID),
    }


@app.get("/media/{nombre}")
def servir_media(nombre: str):
    ruta = (DIR_MEDIA / nombre).resolve()
    if not str(ruta).startswith(str(DIR_MEDIA.resolve())) or not ruta.exists():
        return JSONResponse({"error": "no existe"}, status_code=404)
    tipo = "audio/ogg" if ruta.suffix == ".ogg" else "audio/mpeg"
    return FileResponse(ruta, media_type=tipo)


@app.get("/documentos/{nombre}")
def servir_documento(nombre: str):
    """Respaldo por link cuando no se pudo subir el archivo a Kapso.

    En serverless el disco no sobrevive entre invocaciones, así que esto solo
    responde si el archivo sigue en la misma instancia que lo escribió.
    """
    ruta = (DIR_DOCS / nombre).resolve()
    if not str(ruta).startswith(str(DIR_DOCS.resolve())) or not ruta.exists():
        return JSONResponse({"error": "no existe"}, status_code=404)
    return FileResponse(ruta, media_type=TIPOS_DOC.get(ruta.suffix, "application/octet-stream"),
                        filename=ruta.name)


TIPOS_DOC = {
    ".pdf": "application/pdf",
    ".docx": ("application/vnd.openxmlformats-officedocument"
              ".wordprocessingml.document"),
    ".doc": "application/msword",
    ".txt": "text/plain",
}


# ═══════════════════════════════════════════ fase 1 — webhook de Kapso ═══

async def webhook(
    request: Request,
    tareas: BackgroundTasks,
    x_webhook_event: str | None = Header(default=None),
    x_webhook_signature: str | None = Header(default=None),
    x_idempotency_key: str | None = Header(default=None),
):
    """Responde en milisegundos. No hace trabajo pesado aquí."""
    crudo = await request.body()
    log.info(
        "webhook recibido evento=%s bytes=%d idempotencia=%s",
        x_webhook_event or "(sin header)",
        len(crudo),
        bool(x_idempotency_key),
    )

    if not kapso.firma_valida(crudo, x_webhook_signature):
        log.warning("firma inválida — rechazado")
        return JSONResponse({"ok": False, "error": "firma"}, status_code=401)

    if _ya_procesado(x_idempotency_key):
        log.info("webhook duplicado ignorado: %s", x_idempotency_key)
        return {"ok": True, "nota": "duplicado"}

    try:
        payload = await request.json()
    except Exception:
        log.warning("webhook ignorado: cuerpo no JSON")
        return {"ok": True, "nota": "cuerpo no json"}

    normalizados = list(map(kapso.leer_mensaje, kapso.extraer_mensajes(payload)))
    pendientes = [
        m for m in normalizados
        if m["direccion"] == "inbound" and m.get("telefono")
    ]
    log.info(
        "evento %s — %d normalizado(s), %d entrante(s): %s",
        x_webhook_event or "(sin header)",
        len(normalizados),
        len(pendientes),
        [
            {"id": m.get("id"), "tipo": m.get("tipo"),
             "direccion": m.get("direccion"), "telefono": bool(m.get("telefono"))}
            for m in normalizados
        ],
    )

    if config.MODO_PROCESO == "http" and config.PUBLIC_BASE_URL:
        await asyncio.gather(*(_disparar_tarea(m) for m in pendientes))
    else:
        if config.MODO_PROCESO == "http":
            log.error("MODO_PROCESO=http sin URL publica; se procesa en segundo "
                      "plano (en serverless esto no termina)")
        for msg in pendientes:
            tareas.add_task(procesar, msg)

    return {"ok": True, "encolados": len(pendientes)}


app.add_api_route(config.WEBHOOK_PATH, webhook, methods=["POST"])
if config.WEBHOOK_PATH != "/webhooks/whatsapp":
    app.add_api_route("/webhooks/whatsapp", webhook, methods=["POST"])


async def _disparar_tarea(msg: dict) -> None:
    """Auto-invocación: arranca una segunda función y no espera la respuesta.

    Se espera un poco a propósito para que la petición salga entera; el
    timeout de lectura que salta después es lo normal y se ignora: la segunda
    función ya tiene el cuerpo y sigue trabajando por su cuenta.
    """
    url = f"{config.PUBLIC_BASE_URL}{config.TAREA_PATH}"
    tiempos = httpx.Timeout(read=3.0, connect=5.0, write=5.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=tiempos) as c:
            r = await c.post(
                url, json=msg,
                headers={"Authorization": f"Bearer {config.API_TOKEN}"})
        if r.status_code >= 400:
            log.error("la tarea respondió %s → %s", r.status_code, r.text[:200])
    except httpx.TimeoutException:
        log.info("tarea disparada (sin esperar respuesta)")
    except Exception as e:
        log.error("no se pudo disparar la tarea: %s", e)


# ═════════════════════════════════════════ fase 2 — trabajo de verdad ═══

@app.post(config.TAREA_PATH)
async def tarea_procesar(request: Request,
                         authorization: str | None = Header(default=None)):
    """Interno. Aquí sí se puede tardar (Vercel: hasta maxDuration)."""
    if not _autorizado(authorization):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    msg = await request.json()
    await run_in_threadpool(procesar, msg)
    return {"ok": True}


def procesar(msg: dict) -> None:
    """Transcribe → pregunta al backend → ejecuta lo que diga."""
    telefono = msg.get("telefono")
    if not telefono:
        return

    try:
        entrada = _construir_entrada(msg)
        acciones = backend.procesar(entrada)
        log.info("backend devolvió %d acción(es)", len(acciones))
        for accion in acciones:
            _ejecutar(telefono, accion)
    except Exception:
        log.exception("fallo procesando")
        try:
            kapso.enviar_texto(
                telefono, "Algo falló de nuestro lado. Inténtelo otra vez.")
        except Exception:
            log.exception("tampoco pude avisar del fallo")


def _construir_entrada(msg: dict) -> dict:
    """Arma el mensaje que se le manda al backend."""
    entrada = {
        "telefono": msg.get("telefono"),
        "mensaje_id": msg.get("id"),
        "tipo": msg.get("tipo"),
        "texto": (msg.get("texto") or "").strip(),
        "timestamp": msg.get("timestamp"),
        "transcripcion": None,
    }

    if msg.get("tipo") == "audio" and msg.get("media_url"):
        audio = kapso.descargar_media(msg["media_url"])
        log.info("audio %d bytes (%s)", len(audio), msg.get("media_tipo"))
        t0 = time.time()
        tr = voz.transcribir(
            audio,
            nombre=msg.get("media_nombre") or "audio.ogg",
            content_type=msg.get("media_tipo") or "audio/ogg",
        )
        log.info("STT %.1fs conf=%.2f: %s", time.time() - t0,
                 tr["confianza"], tr["texto"][:120])
        tr["baja_confianza"] = tr["confianza"] < config.UMBRAL_CONFIANZA_STT
        tr["texto_kapso"] = msg.get("transcripcion_kapso")
        entrada["transcripcion"] = tr
        entrada["texto"] = tr["texto"]

    return entrada


def _ejecutar(telefono: str, accion: dict) -> None:
    """Ejecuta una acción devuelta por el backend."""
    tipo = accion.get("tipo")

    if tipo == "texto":
        kapso.enviar_texto(telefono, accion.get("texto", ""))

    elif tipo == "audio":
        enviar_voz(telefono, accion.get("texto", ""), accion.get("voice_id"))

    elif tipo == "documento":
        enviar_documento(telefono, accion)

    else:
        log.warning("acción desconocida: %s", tipo)


def enviar_documento(telefono: str, accion: dict) -> None:
    """Manda un documento. Acepta tres formas, en este orden:

        {"archivo": "salidas/x.docx"}   ruta en disco (backend en proceso)
        {"contenido_b64": "..."}        bytes en base64 (backend remoto)
        {"url": "https://..."}          link público (lo descarga WhatsApp)

    Las dos primeras se suben a Kapso y se mandan por media_id: así el archivo
    no depende de que este proceso siga vivo cuando WhatsApp vaya a buscarlo,
    que es justo lo que no se cumple en serverless.
    """
    nombre = accion.get("nombre") or "documento.pdf"
    descripcion = accion.get("descripcion") or ""

    contenido: bytes | None = None
    if ruta := accion.get("archivo"):
        try:
            contenido = Path(ruta).read_bytes()
        except OSError as e:
            log.error("no pude leer el documento %s: %s", ruta, e)
    elif b64 := accion.get("contenido_b64"):
        try:
            contenido = base64.b64decode(b64)
        except Exception as e:
            log.error("contenido_b64 inválido: %s", e)

    if contenido:
        tipo_mime = accion.get("content_type") or TIPOS_DOC.get(
            Path(nombre).suffix.lower(), "application/octet-stream")
        log.info("documento %s — %d bytes (%s)", nombre, len(contenido), tipo_mime)

        media_id = kapso.subir_media(contenido, nombre, tipo_mime)
        if media_id:
            kapso.enviar_documento_por_id(telefono, media_id, nombre, descripcion)
            return

        # Respaldo: servirlo desde aquí. Solo sirve con URL pública y disco vivo.
        if config.PUBLIC_BASE_URL:
            local = DIR_DOCS / f"{uuid.uuid4().hex}{Path(nombre).suffix}"
            try:
                local.write_bytes(contenido)
                kapso.enviar_documento(
                    telefono, f"{config.PUBLIC_BASE_URL}/documentos/{local.name}",
                    nombre, descripcion)
                return
            except OSError as e:
                log.error("tampoco pude guardar el documento: %s", e)

        kapso.enviar_texto(
            telefono,
            "Su documento quedó listo pero no logré enviárselo por aquí. "
            "Escríbanos y se lo hacemos llegar.")
        return

    if url := accion.get("url"):
        kapso.enviar_documento(telefono, url, nombre, descripcion)
        return

    log.error("acción documento sin archivo, contenido_b64 ni url")


def enviar_voz(telefono: str, texto: str, voice_id: str | None = None) -> None:
    """TTS y envío. Prefiere subir el audio (funciona sin disco ni URL)."""
    if not texto.strip():
        return
    audio, tipo, ext = voz.sintetizar(texto, voice_id)
    log.info("TTS %d bytes (%s)", len(audio), tipo)

    media_id = kapso.subir_media(audio, f"voz.{ext}", tipo)
    if media_id:
        kapso.enviar_audio_por_id(telefono, media_id, nota_de_voz=(ext == "ogg"))
        return

    # Respaldo: servirlo desde el propio servidor. No sirve en serverless.
    if not config.PUBLIC_BASE_URL:
        log.error("no se pudo subir el audio y no hay URL pública")
        kapso.enviar_texto(telefono, texto)
        return
    nombre = f"{uuid.uuid4().hex}.{ext}"
    (DIR_MEDIA / nombre).write_bytes(audio)
    kapso.enviar_audio_por_link(
        telefono, f"{config.PUBLIC_BASE_URL}/media/{nombre}")


# ═══════════════════════════════════════════ API para el backend ═══

@app.post("/api/enviar")
async def api_enviar(request: Request,
                     authorization: str | None = Header(default=None)):
    """El backend manda un mensaje cuando quiera (recordatorios, avisos...).

    {"telefono": "...", "tipo": "texto"|"audio"|"documento", ...}
    Acepta también {"acciones": [ ... ]} para varias de una.
    """
    if not _autorizado(authorization):
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    cuerpo = await request.json()
    telefono = cuerpo.get("telefono")
    if not telefono:
        return JSONResponse({"error": "falta telefono"}, status_code=400)

    acciones = cuerpo.get("acciones") or [cuerpo]
    enviadas = 0
    for accion in acciones:
        try:
            _ejecutar(telefono, accion)
            enviadas += 1
        except Exception as e:
            log.exception("fallo enviando")
            return JSONResponse(
                {"error": str(e), "enviadas": enviadas}, status_code=502)
    return {"ok": True, "enviadas": enviadas}


def _error(e: Exception, contexto: str) -> JSONResponse:
    """Devuelve el fallo legible en vez de un 500 pelado."""
    log.exception(contexto)
    detalle = str(e)
    if isinstance(e, httpx.HTTPStatusError):
        detalle = f"{e.response.status_code}: {e.response.text[:300]}"
    return JSONResponse({"error": contexto, "detalle": detalle}, status_code=502)


@app.post("/api/voz")
async def api_voz(request: Request,
                  authorization: str | None = Header(default=None)):
    """Texto → audio. Con `telefono` lo envía; sin él, devuelve el mp3/ogg."""
    if not _autorizado(authorization):
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    cuerpo = await request.json()
    texto = (cuerpo.get("texto") or "").strip()
    if not texto:
        return JSONResponse({"error": "falta texto"}, status_code=400)

    try:
        if telefono := cuerpo.get("telefono"):
            enviar_voz(telefono, texto, cuerpo.get("voice_id"))
            return {"ok": True, "enviado_a": telefono}
        audio, tipo, _ = voz.sintetizar(texto, cuerpo.get("voice_id"))
    except Exception as e:
        return _error(e, "no se pudo generar la voz")

    return Response(content=audio, media_type=tipo)


@app.post("/api/transcribir")
async def api_transcribir(
    archivo: UploadFile = File(...),
    idioma: str = Form(default=""),
    authorization: str | None = Header(default=None),
):
    """Audio (multipart) → {texto, duracion, confianza, idioma}."""
    if not _autorizado(authorization):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    try:
        return voz.transcribir(
            await archivo.read(),
            nombre=archivo.filename or "audio.ogg",
            content_type=archivo.content_type or "audio/ogg",
        )
    except Exception as e:
        return _error(e, "no se pudo transcribir")


@app.get("/api/voces")
def api_voces(authorization: str | None = Header(default=None)):
    """Voces disponibles, para escoger ELEVENLABS_VOICE_ID."""
    if not _autorizado(authorization):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    try:
        return {"voces": voz.listar_voces()}
    except Exception as e:
        return _error(e, "no se pudieron listar las voces")


# ═══════════════════════════════════════════════════════════ arranque ═══

def al_arrancar() -> None:
    faltan = config.faltantes()
    url = config.url_webhook()
    barra = "=" * 66
    lineas = [
        "", barra, "  PUENTE TUTELA VOZ", barra,
        "  Faltan en .env: " + ", ".join(faltan) if faltan else "  Llaves cargadas",
        f"  URL publica : {config.PUBLIC_BASE_URL or '(falta)'}  [{config.ORIGEN_BASE_URL}]",
        f"  Modo        : {config.MODO_PROCESO}",
        f"  Backend     : {backend.modo()}",
        "-" * 66,
    ]
    if url:
        lineas += ["  PEGA ESTO EN KAPSO -> Endpoint URL:", "", f"      {url}", ""]
    else:
        lineas += ["  Sin URL publica. En local:  python arrancar.py"]
    lineas += [barra, ""]
    print("\n".join(lineas), flush=True)
