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
from canal.consentimientos import VERSION_AVISO, registrar as registrar_consentimiento
from core.bot_core import procesar_texto
from core.estado import marcar_pregunta, registrar_mensaje
from core.preguntas import PREGUNTAS_DATOS
from datos.canales_salud import resolver_canal
from juridico import campos
from juridico.revisor_agente import RevisionAgenteError, revisar_documento
from juridico.revision import revisar_contexto
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
    "Gracias por comunicarse con Temis. Con mucho gusto le ayudaré. "
    "Cuando se sienta listo, por favor cuénteme desde el principio qué ocurrió "
    "con su EPS. Puede escribir o enviarme una nota de voz, sin afán."
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


def _aviso_consentimiento() -> str:
    responsable = config.RESPONSABLE_DATOS
    contacto = (
        f"Puede ejercer sus derechos escribiendo a {config.CORREO_PRIVACIDAD}. "
        if config.CORREO_PRIVACIDAD else
        "Puede solicitar información, corrección, eliminación o revocación por este chat. "
    )
    politica = (
        f"La política de tratamiento está disponible aquí: {config.URL_POLITICA_DATOS}. "
        if config.URL_POLITICA_DATOS else ""
    )
    return (
        f"Antes de comenzar, {responsable} necesita su autorización para tratar "
        "datos personales sensibles, incluidos su voz, identificación, información "
        "de salud y documentos del caso. Los usaremos únicamente para transcribir "
        "su relato, orientarle y preparar el documento jurídico que usted solicite. "
        "Para prestar el servicio podrán procesarlos Kapso, ElevenLabs y Anthropic. "
        "Autorizar es voluntario; puede negarse, consultar sus datos, corregirlos, "
        "pedir su eliminación o revocar la autorización. " + contacto + politica +
        "Si está de acuerdo, por favor responda exactamente: AUTORIZO. "
        "Si no está de acuerdo, responda: NO AUTORIZO."
    )


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
        {"tipo": "audio", "texto": _texto_para_voz(texto)},
    ]


def _pedir_consentimiento(prefacio: str = "") -> list[dict]:
    texto = (prefacio + _aviso_consentimiento()).strip()
    return [
        {
            "tipo": "botones",
            "encabezado": "Consentimiento informado",
            "texto": texto,
            "pie": "Seleccione una opción para continuar.",
            "botones": [
                {"id": "consentimiento_autorizar", "titulo": "Autorizar"},
                {"id": "consentimiento_rechazar", "titulo": "No autorizar"},
            ],
        },
        {"tipo": "audio", "texto": _texto_para_voz(
            "Antes de comenzar necesito su autorización para tratar sus datos. "
            "Por favor seleccione Autorizar o No autorizar en el mensaje escrito.")},
    ]


def _texto_para_voz(texto: str) -> str:
    """Quita datos incómodos de deletrear; permanecen visibles en el chat."""
    hablado = re.sub(
        r"https?://\S+",
        "el enlace que le dejé escrito en el chat",
        texto,
        flags=re.IGNORECASE,
    )
    hablado = re.sub(
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        "que le dejé escrito en el chat",
        hablado,
    )
    return hablado


# ============================================================
# TURNO
# ============================================================

def procesar_turno(telefono: str, texto: str, transcripcion: dict | None = None,
                   client=None, mensaje_id: str | None = None) -> list[dict]:
    """Un mensaje entra, una lista de acciones sale."""
    texto = (texto or "").strip()

    if _normalizar(texto) in REINICIOS:
        sesiones.borrar(telefono)
        caso = sesiones.obtener(telefono)
        sesiones.guardar(telefono, caso)
        return _pedir_consentimiento("Con gusto empezamos desde cero. ")

    caso = sesiones.obtener(telefono)
    consentimiento = caso.get("consentimiento") or {}
    if not consentimiento.get("otorgado"):
        respuesta = _normalizar(texto)
        if "no autorizo" in respuesta:
            sesiones.borrar(telefono)
            return _decir(
                "Entiendo y respeto su decisión. No procesaremos la información "
                "de su caso. Si después desea continuar, puede volver a escribirnos.")
        if respuesta in {"autorizo", "si autorizo", "autorizo el tratamiento",
                         "autorizo el tratamiento de mis datos"}:
            constancia = registrar_consentimiento(telefono, mensaje_id, texto)
            caso["consentimiento"] = {
                "otorgado": True,
                "version": VERSION_AVISO,
                "fecha": constancia["fecha"],
                "mensaje_id": mensaje_id,
                "respuesta": texto,
            }
            sesiones.guardar(telefono, caso)
            return _decir("Muchas gracias por autorizar el tratamiento de sus datos. " + SALUDO)
        sesiones.guardar(telefono, caso)
        return _pedir_consentimiento()

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
            "Disculpe, no logré entender el audio. ¿Podría repetirlo más despacio, por favor?")

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
                pregunta = "Disculpe, no logré entender esa respuesta. Intentemos una vez más, por favor. " + pregunta
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
        datos_documento = {**datos, **caso.get("slots", {})}
        contexto = campos.contexto(tipo, datos_documento, telefono=telefono)
        contexto = revisar_contexto(tipo, contexto)
        revisiones = contexto.pop("_revisiones", [])
        archivo = DIR_SALIDAS / f"{uuid.uuid4().hex}_{tipo}.docx"
        render = renderizar_documento(
            tipo=tipo, datos=contexto, salida=archivo, resolver_juzgado=False)
        revision_final = revisar_documento(tipo, render["archivo"], contexto)
        if revision_final.get("modo") == "agente":
            log.info("revisión jurídica final: %s", revision_final.get("decision"))
    except RevisionAgenteError as exc:
        log.warning("documento bloqueado por revisión jurídica: %s", exc)
        return caso, _decir(
            "Antes de entregarle la tutela necesito corregir algo: " + str(exc))
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
        {"tipo": "audio", "texto": _texto_para_voz(resumen)},
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
