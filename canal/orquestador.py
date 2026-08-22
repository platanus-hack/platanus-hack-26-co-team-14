"""
Un turno de conversación, de principio a fin.

    texto de la usuaria
        → core (extracción + triage + qué preguntar)
        → juridico (qué minuta, qué falta, cómo se rellena)
        → lista de acciones para el canal

La lista de acciones es el contrato del puente: `{"tipo": "texto"|"audio"|
"documento", ...}`. Quien las ejecuta es `puente/app.py`; aquí solo se decide
qué decir.

Este módulo no habla con Kapso ni con ElevenLabs. No sabe que existe WhatsApp.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import unicodedata
import uuid
from pathlib import Path

from canal import sesiones
from core.bot_core import procesar_texto
from core.estado import marcar_pregunta, registrar_mensaje
from core.preguntas import PREGUNTAS_DATOS
from datos.canales_salud import resolver_canal
from juridico import campos
from juridico.render import renderizar_documento

log = logging.getLogger("orquestador")

# En serverless el proyecto está montado de solo lectura: lo único escribible
# es el temporal. Y da igual que sea efímero, porque el documento se sube a
# Kapso en esta misma invocación.
DIR_SALIDAS = (
    Path(tempfile.gettempdir()) / "tutela_salidas"
    if (os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))
    else Path(campos.__file__).resolve().parent.parent / "salidas"
)


# ============================================================
# TEXTOS FIJOS
# ============================================================

SALUDO = (
    "Buenos días. Soy el asistente de Temis. "
    "Cuénteme con sus palabras qué le pasó con su EPS: "
    "puede mandarme una nota de voz, sin apuro."
)

# Sin dato verificado, esta salida siempre es válida: están obligados a
# recibir el documento y a remitirlo.
FALLBACK_RADICACION = (
    "Lleve el documento a la personería municipal, a la Defensoría del Pueblo "
    "o a cualquier juzgado. Están obligados a recibírselo y a remitirlo."
)

REINICIOS = {"reiniciar", "empezar de nuevo", "empezar de cero", "borrar todo",
             "otra vez desde el principio", "nuevo caso", "cancelar"}

SALUDOS_SIMPLES = {
    "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
    "buen dia", "hola buenos dias", "hola buenas tardes", "hola buenas noches",
}

# Rutas que no terminan en un documento: lo que se entrega es una indicación.
# En cuanto el triage las decide, se contesta. Seguir pidiendo cédula y
# dirección para acabar diciendo «radique aquí» es hacerle perder el tiempo a
# alguien que ya nos contó su problema.
SIN_DOCUMENTO = {"peticion", "pqrd", "esperar", "desacato"}


def _normalizar(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", (texto or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", plano).split())


def _pregunta_sobre_radicacion(texto: str) -> bool:
    """Preguntas laterales que no son la respuesta al dato pendiente."""
    plano = _normalizar(texto)
    menciona_destino = any(p in plano for p in (
        "donde envio", "donde enviar", "a donde envio", "a donde enviar",
        "donde entrego", "donde entregar", "donde radico", "donde radicar",
        "correo electronico", "algun correo",
    ))
    return menciona_destino and any(
        p in plano for p in ("env", "entreg", "radic", "correo")
    )


# ============================================================
# ACCIONES
# ============================================================

def _decir(texto: str) -> list[dict]:
    """Lo mismo escrito y hablado.

    Escrito porque queda y se puede releer; hablado porque hay quien no lee.
    Ese es el canal entero: no se escoge uno de los dos.
    """
    return [
        {"tipo": "texto", "texto": texto},
        {"tipo": "audio", "texto": texto},
    ]


# ============================================================
# TURNO
# ============================================================

def procesar_turno(telefono: str, texto: str, transcripcion: dict | None = None,
                   client=None) -> list[dict]:
    """Un mensaje entra, una lista de acciones sale."""
    texto = (texto or "").strip()

    if _normalizar(texto) in REINICIOS:
        sesiones.borrar(telefono)
        return _decir("Listo, empezamos de cero. " + SALUDO)

    caso = sesiones.obtener(telefono)
    primera_vez = not caso.get("mensajes")
    esperando_antes = caso.get("esperando")

    # Un saludo no es la historia clínica ni jurídica. Se responde y se espera
    # el relato antes de activar extracción y triage.
    if primera_vez and _normalizar(texto) in SALUDOS_SIMPLES:
        caso = registrar_mensaje(caso, rol="usuario", texto=texto)
        caso = registrar_mensaje(caso, rol="asistente", texto=SALUDO)
        sesiones.guardar(telefono, caso)
        return _decir(SALUDO)

    # La persona puede hacer una pregunta durante el formulario. Se responde
    # sin pasarla por extracción ni perder el dato que todavía falta.
    if esperando_antes and _pregunta_sobre_radicacion(texto):
        pregunta_pendiente = PREGUNTAS_DATOS.get(esperando_antes)
        if pregunta_pendiente is None:
            from core.preguntas import PREGUNTAS_TRIAGE
            pregunta_pendiente = PREGUNTAS_TRIAGE.get(esperando_antes)
        respuesta = (
            "Cuando terminemos, le enviaré el documento por este mismo chat. "
            "También le indicaré el correo electrónico del juzgado si está "
            "verificado. Usted podrá enviarlo allí o llevarlo a la personería, "
            "a la Defensoría del Pueblo o a un juzgado. "
            "Para continuar: " + (pregunta_pendiente or "necesito el dato que le pregunté antes.")
        )
        return _decir(respuesta)

    if not texto:
        return _decir(
            "No logré entender el audio. ¿Me lo puede repetir más despacio?")

    try:
        resultado = procesar_texto(caso, texto, client=client)
    except Exception:
        log.exception("falló la extracción")
        return _decir(
            "Tuve un problema entendiendo lo que me dijo. "
            "¿Me lo puede repetir?")

    caso = resultado["caso"]
    accion = resultado["accion"]

    acciones: list[dict] = []

    if _dudoso(transcripcion):
        acciones.append({
            "tipo": "texto",
            "texto": f"Entendí esto: «{texto}». Si me equivoqué, dígamelo.",
        })

    if caso.get("ruta") in SIN_DOCUMENTO:
        caso, salida = _cerrar_caso(telefono, caso)
        _persistir(telefono, caso)
        return acciones + salida

    if accion["accion"] == "preguntar":
        slot = accion["slot"]
        pregunta = accion["texto"]
        if esperando_antes == slot:
            intentos = caso.setdefault("intentos_fallidos", {})
            intentos[slot] = intentos.get(slot, 0) + 1
            if intentos[slot] >= 2:
                pregunta = (
                    "Todavía no logré entender esa respuesta. Si le es posible, "
                    "escríbamela aquí por WhatsApp. " + pregunta
                )
            else:
                pregunta = "No logré entender esa respuesta. Intentemos una vez más. " + pregunta
        acciones += _decir(pregunta)
        sesiones.guardar(telefono, caso)
        return acciones

    if accion["accion"] == "generar_documento":
        caso, salida = _cerrar_caso(telefono, caso)
        _persistir(telefono, caso)
        return acciones + salida

    log.warning("acción sin salida: %s", accion)
    sesiones.guardar(telefono, caso)
    return acciones + _decir(
        "Necesito un dato más para poder ayudarle. "
        "¿Me puede contar otra vez qué fue lo que pasó con su EPS?")


def _dudoso(transcripcion: dict | None) -> bool:
    return bool(transcripcion and transcripcion.get("baja_confianza"))


def _persistir(telefono: str, caso: dict) -> None:
    """Guarda el caso, salvo que ya haya cumplido su función."""
    if caso.pop("_cerrado", False):
        sesiones.borrar(telefono)
        return
    sesiones.guardar(telefono, caso)


# ============================================================
# CIERRE: LA RUTA YA ESTÁ DECIDIDA
# ============================================================

def _cerrar_caso(telefono: str, caso: dict) -> tuple[dict, list[dict]]:
    """Devuelve (caso, acciones). El caso puede volver con una pregunta más:
    las minutas piden datos que el triage no necesitaba."""
    ruta = caso.get("ruta")
    datos = caso.get("datos", {})

    if ruta == "tutela":
        return _cerrar_tutela(telefono, caso, datos)

    if ruta in {"pqrd", "peticion"}:
        return caso, _cerrar_peticion(ruta, datos)

    if ruta == "esperar":
        return caso, _decir(
            "Su petición ya está radicada y el plazo todavía no se vence. "
            "La EPS tiene 15 días hábiles para responderle. "
            "Guarde la copia radicada y, si se cumple el plazo sin respuesta, "
            "vuelva y seguimos.")

    if ruta == "desacato":
        return caso, _cerrar_desacato(datos)

    log.error("ruta desconocida al cerrar: %s", ruta)
    return caso, _decir(
        "No pude determinar el camino correcto para su caso. " + FALLBACK_RADICACION)


# ── tutela ───────────────────────────────────────────────────────────────

def _cerrar_tutela(telefono: str, caso: dict,
                   datos: dict) -> tuple[dict, list[dict]]:
    tipo = campos.tipo_documento(datos)

    if tipo is None:
        return _preguntar(caso, "paciente")

    if pendientes := campos.faltantes(tipo, datos):
        return _preguntar(caso, pendientes[0])

    try:
        contexto = campos.contexto(tipo, datos, telefono=telefono)
        revisiones = contexto.pop("_revisiones", [])
        archivo = DIR_SALIDAS / f"{uuid.uuid4().hex}_{tipo}.docx"
        render = renderizar_documento(
            tipo=tipo, datos=contexto, salida=archivo, resolver_juzgado=False)
    except Exception:
        log.exception("no se pudo generar el documento (%s)", tipo)
        return caso, _decir(
            "Tengo toda su información pero el documento no me salió bien. "
            "No le voy a mandar algo incompleto. " + FALLBACK_RADICACION)

    resumen = _resumen_tutela(render, revisiones, datos)

    acciones = [
        {"tipo": "texto", "texto": resumen},
        {"tipo": "documento",
         "archivo": render["archivo"],
         "nombre": "tutela.docx",
         "descripcion": "Su acción de tutela, lista para revisar y radicar."},
        {"tipo": "audio", "texto": resumen},
    ]

    # El caso cumplió su función. No guardamos datos de salud más tiempo del
    # que hace falta (Ley 1581 de 2012, art. 5): lo borra `_persistir`.
    caso["_cerrado"] = True
    return caso, acciones


def _resumen_tutela(render: dict, revisiones: list[str], datos: dict) -> str:
    lineas = ["Le mandé su acción de tutela. Léala antes de radicarla."]

    juez = render.get("juez_destino")
    correo = render.get("email_juzgado")

    if correo:
        lineas.append(
            f"Va dirigida al {juez}. Puede enviarla al correo electrónico {correo}, "
            f"o llevarla en persona.")
    else:
        lineas.append(f"Va dirigida al {juez}. " + FALLBACK_RADICACION)

    lineas.append(
        "Recuerde: la tutela la tiene que presentar usted. "
        "Nosotros no la radicamos.")

    canal_eps = resolver_canal(datos.get("eps") or "").get("canal")
    if canal_eps and canal_eps.get("url"):
        lineas.append(
            "No necesita enviar la tutela a la EPS: el juzgado se encargará "
            "de notificarla. Si además necesita comunicarse con la EPS, el "
            f"canal oficial verificado de {canal_eps['nombre']} es "
            f"{canal_eps['url']}.")

    if revisiones:
        lineas.append("Antes de firmarla, revise esto: " + " ".join(revisiones))

    return " ".join(lineas)


# ── petición y PQRD ──────────────────────────────────────────────────────

def _cerrar_peticion(ruta: str, datos: dict) -> list[dict]:
    entidad = datos.get("eps") or datos.get("ips") or ""
    canal = resolver_canal(entidad).get("canal")

    que_es = ("un derecho de petición" if ruta == "peticion"
              else "una queja formal ante su EPS")

    if not canal:
        return _decir(
            f"Lo que le corresponde ahora es {que_es}. "
            f"No tengo un canal verificado para «{entidad}» y no le voy a "
            f"inventar uno. " + FALLBACK_RADICACION)

    return _decir(
        f"Lo que le corresponde ahora es {que_es}. "
        f"Radíquelo en {canal['nombre']}, en {canal['url']}. "
        f"Pida siempre el número de radicado y guárdelo: "
        f"es la prueba de que pidió, y sin ella la tutela cuesta más.")


# ── desacato ─────────────────────────────────────────────────────────────

def _cerrar_desacato(datos: dict) -> list[dict]:
    juzgado = datos.get("juzgado_fallo")
    radicado = datos.get("radicado")

    detalle = ""
    if juzgado:
        detalle = f" Se presenta ante el mismo despacho que falló: {juzgado}."
        if radicado:
            detalle += f" Cite el radicado {radicado}."

    return _decir(
        "Si un juez ya le dio la razón y la EPS no cumplió, lo que procede es "
        "un incidente de desacato, no otra tutela." + detalle +
        " Todavía no tengo la minuta de desacato preparada, así que no le voy "
        "a entregar un documento a medias. " + FALLBACK_RADICACION)


# ── preguntar un dato que pide la minuta ─────────────────────────────────

def _preguntar(caso: dict, slot: str) -> tuple[dict, list[dict]]:
    """Pide un dato que el triage no necesitaba pero la minuta sí."""
    caso = marcar_pregunta(caso, slot)
    pregunta = PREGUNTAS_DATOS.get(slot, f"Necesito un dato más: {slot}.")
    return caso, _decir(pregunta)


# ============================================================
# COMPATIBILIDAD
# ============================================================
# La versión anterior exponía estas dos funciones. Se mantienen para no
# romper nada que todavía las llame.

def procesar_turno_core(usuario_id: str, texto: str) -> dict:
    caso = sesiones.obtener(usuario_id)
    resultado = procesar_texto(caso, texto)
    sesiones.guardar(usuario_id, resultado["caso"])
    return resultado


def construir_respuesta_final(usuario_id: str, resultado: dict) -> list[dict]:
    caso = resultado["caso"]

    if resultado.get("respuesta"):
        return _decir(resultado["respuesta"])

    caso, acciones = _cerrar_caso(usuario_id, caso)
    _persistir(usuario_id, caso)
    return acciones
