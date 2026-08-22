"""
Puente entre el caso conversacional y los placeholders de las minutas.

El caso guarda lo que dijo la persona (`nombre_completo`, `servicio_negado`…).
Las minutas piden otra cosa (`nombre_agente`, `servicio_urgente`, `dia_orden`…).
Este módulo traduce lo uno en lo otro.

Aquí NO entra el modelo. Todo es tabla, lookup o derivación aritmética:

    caso.datos  ──mapeo fijo──>  {{placeholders}}  ──render.py──>  DOCX

Responde a tres preguntas, y solo a esas:

    tipo_documento(datos)      qué minuta corresponde
    faltantes(tipo, datos)     qué queda por preguntar antes de poder generar
    contexto(tipo, datos, tel) los valores finales que recibe la plantilla
"""

from __future__ import annotations

import re
import unicodedata

from datos.canales_salud import resolver_canal
from datos.juzgados import contexto_juzgado


# ============================================================
# QUÉ MINUTA
# ============================================================

# Las dos minutas preparadas son de AGENCIA OFICIOSA: quien firma actúa a
# nombre de otro. No hay minuta para quien tutela por sí mismo, y no se
# inventa una: se avisa y se para.
TIPOS = {
    "yo": "tutela_propia",
    "menor": "tutela_menor",
    "otro": "tutela_agente",
}

# Compatibilidad con consumidores antiguos. Ahora sí existe la plantilla.
SIN_PLANTILLA = "tutela_propia"


def tipo_documento(datos: dict) -> str | None:
    """Qué plantilla corresponde. None = todavía no se sabe.

    Devuelve SIN_PLANTILLA cuando la tutela es para quien habla: la ruta es
    correcta pero no existe minuta, y el caso no puede terminar en un DOCX.
    """
    paciente = (datos.get("paciente") or "").strip().lower()

    if paciente in TIPOS:
        return TIPOS[paciente]

    # Sin respuesta explícita, un nombre de agenciado ya lo dice.
    if datos.get("nombre_menor"):
        return TIPOS["menor"]

    if datos.get("nombre_agenciado"):
        return TIPOS["otro"]

    return None


# ============================================================
# QUÉ HACE FALTA PREGUNTAR
# ============================================================

# En orden de pregunta. Lo que identifica a la persona primero, el relato
# después: nadie cuenta su historia y luego deletrea una cédula.
REQUERIDOS = {
    "tutela_propia": [
        "nombre_completo",
        "cedula",
        "lugar_expedicion",
        "eps",
        "diagnostico",
        "servicio_negado",
        "fecha_orden",
        "hecho_vulneracion",
        "ciudad_vulneracion",
        "direccion_notificaciones",
    ],
    "tutela_menor": [
        "nombre_completo",
        "cedula",
        "lugar_expedicion",
        "nombre_menor",
        "registro_civil_menor",
        "edad_menor",
        "eps",
        "diagnostico",
        "servicio_negado",
        "fecha_orden",
        "hecho_vulneracion",
        "ciudad_vulneracion",
        "direccion_notificaciones",
    ],

    "tutela_agente": [
        "nombre_completo",
        "cedula",
        "lugar_expedicion",
        "nombre_agenciado",
        "cedula_agenciado",
        "lugar_expedicion_agenciado",
        "edad_agenciado",
        "relacion_agente_agenciado",
        "eps",
        "diagnostico",
        "servicio_negado",
        "fecha_orden",
        "hecho_vulneracion",
        "ciudad_vulneracion",
        "direccion_notificaciones",
    ],
}


def faltantes(tipo: str, datos: dict) -> list[str]:
    """Campos del caso que la minuta necesita y todavía no tenemos."""
    return [
        campo for campo in REQUERIDOS.get(tipo, [])
        if not str(datos.get(campo) or "").strip()
    ]


# ============================================================
# NÚMEROS A LETRAS
# ============================================================

_UNIDADES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete",
             "ocho", "nueve", "diez", "once", "doce", "trece", "catorce",
             "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve",
             "veinte", "veintiuno", "veintidós", "veintitrés", "veinticuatro",
             "veinticinco", "veintiséis", "veintisiete", "veintiocho",
             "veintinueve"]

_DECENAS = {30: "treinta", 40: "cuarenta", 50: "cincuenta", 60: "sesenta",
            70: "setenta", 80: "ochenta", 90: "noventa"}


def numero_a_letras(n) -> str | None:
    """Entero 0–120 en palabras. None si no es un entero de ese rango.

    La minuta del menor pide la edad dos veces, en letras y en número:
    «tiene {{edad_menor_texto}} ({{edad_menor_numero}}) años».
    """
    try:
        n = int(str(n).strip())
    except (TypeError, ValueError):
        return None

    if not 0 <= n <= 120:
        return None

    if n < 30:
        return _UNIDADES[n]

    if n < 100:
        decena, unidad = (n // 10) * 10, n % 10
        if unidad == 0:
            return _DECENAS[decena]
        return f"{_DECENAS[decena]} y {_UNIDADES[unidad]}"

    if n == 100:
        return "cien"

    resto = numero_a_letras(n - 100)
    return f"ciento {resto}"


def solo_digitos(valor) -> str | None:
    """La edad puede llegar como «78 años». Nos quedamos con el número."""
    if valor is None:
        return None
    encontrados = re.findall(r"\d+", str(valor))
    return encontrados[0] if encontrados else None


# ============================================================
# FECHAS
# ============================================================

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_ALIAS_MES = {m[:3]: i + 1 for i, m in enumerate(MESES)}

# Cómo se dice de verdad. "setiembre" se oye tanto como "septiembre", y el STT
# escribe lo que oye.
_VARIANTES = [*MESES, "setiembre"]
_ALIAS_MES["set"] = 9


def _sin_tildes(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in plano if not unicodedata.combining(c))


def partir_fecha(texto) -> tuple[str, str] | None:
    """«12 de marzo», «12/03/2025», «marzo 12» → ("12", "marzo").

    None si no se reconoce. El STT devuelve fechas habladas de muchas formas
    y no todas son una fecha: «antes de Semana Santa» no lo es.
    """
    if not texto:
        return None

    plano = _sin_tildes(str(texto))

    # 12/03/2025 · 12-3-25
    if m := re.search(r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\b", plano):
        dia, mes = int(m.group(1)), int(m.group(2))
        if 1 <= dia <= 31 and 1 <= mes <= 12:
            return str(dia), MESES[mes - 1]

    nombres = "|".join(_sin_tildes(m) for m in _VARIANTES)

    # 12 de marzo
    if m := re.search(rf"\b(\d{{1,2}})\s*(?:de\s+)?({nombres})", plano):
        dia = int(m.group(1))
        mes = _ALIAS_MES[m.group(2)[:3]]
        if 1 <= dia <= 31:
            return str(dia), MESES[mes - 1]

    # marzo 12
    if m := re.search(rf"\b({nombres})\s+(?:de\s+)?(\d{{1,2}})\b", plano):
        dia = int(m.group(2))
        mes = _ALIAS_MES[m.group(1)[:3]]
        if 1 <= dia <= 31:
            return str(dia), MESES[mes - 1]

    return None


# ============================================================
# SERVICIO
# ============================================================

# El mismo dato entra en la minuta en posiciones gramaticales distintas.
# Se escoge la redacción que funciona en la parte resolutiva —«proceda a…»—,
# que es la que el juez ordena.
def _frases_servicio(servicio: str) -> dict:
    servicio = servicio.strip()
    return {
        "servicio_ordenado": servicio,
        "servicio_solicitado": servicio,
        "accion_servicio": f"autorizar y entregar {servicio}",
        "servicio_urgente": f"la autorización y entrega de {servicio}",
    }


# ============================================================
# NOTIFICACIONES
# ============================================================

# No se inventan direcciones ni correos. Con canal verificado se pone el
# canal; sin él se le pide al despacho que notifique donde corresponda, que
# es lo que el juez hace de todos modos.
def _notificacion_entidad(eps: str) -> tuple[str, bool]:
    resultado = resolver_canal(eps)
    canal = resultado.get("canal")

    if canal and canal.get("url"):
        return (f"{canal['nombre']}. Canal de atención: {canal['url']}", False)

    return (
        f"{eps} EPS. Se solicita al despacho notificar en la dirección "
        f"registrada por la entidad ante la Superintendencia Nacional de Salud.",
        True,
    )


def _notificacion_persona(nombre: str, direccion: str, telefono: str | None) -> str:
    partes = [nombre.strip(), direccion.strip()]
    if telefono:
        partes.append(f"Celular: {telefono}")
    return ". ".join(p for p in partes if p) + "."


# ============================================================
# CONTEXTO FINAL
# ============================================================

def contexto(tipo: str, datos: dict, telefono: str | None = None) -> dict:
    """Traduce el caso a los placeholders de la minuta.

    Devuelve además `_revisiones`: la lista de cosas que quedaron resueltas
    por defecto y conviene que un humano mire antes de radicar. render.py la
    ignora; el canal se la cuenta a la usuaria.
    """
    if tipo not in REQUERIDOS:
        raise ValueError(f"No hay mapeo para el tipo: {tipo}")

    revisiones: list[str] = []

    eps = str(datos.get("eps") or "").strip()
    servicio = str(datos.get("servicio_negado") or "").strip()
    nombre = str(datos.get("nombre_completo") or "").strip()
    direccion = str(datos.get("direccion_notificaciones") or "").strip()

    # ── quien firma ──────────────────────────────────────────────────────
    ctx = {
        "nombre_agente": nombre,
        "cedula_agente": str(datos.get("cedula") or "").strip(),
        "lugar_expedicion_agente": str(datos.get("lugar_expedicion") or "").strip(),
        "eps": eps,
        "diagnostico": str(datos.get("diagnostico") or "").strip(),
        "hecho_vulneracion": str(datos.get("hecho_vulneracion") or "").strip(),
        "notificacion_accionante": _notificacion_persona(nombre, direccion, telefono),
    }
    ctx.update(_frases_servicio(servicio))

    # ── a quién se notifica ──────────────────────────────────────────────
    texto_entidad, sin_canal = _notificacion_entidad(eps)
    ctx["notificacion_accionada"] = texto_entidad
    ctx["notificacion_eps"] = texto_entidad
    if sin_canal:
        revisiones.append(
            f"No hay canal verificado para «{eps}»: la notificación queda a "
            f"cargo del despacho.")

    # ── territorio ───────────────────────────────────────────────────────
    ciudad = str(datos.get("ciudad_vulneracion") or "").strip()
    territorio = contexto_juzgado(ciudad=ciudad) if ciudad else {}

    ctx["ciudad_vulneracion"] = ciudad

    # El juzgado se resuelve aquí, una sola vez. render.py recibe el
    # resultado ya hecho (resolver_juzgado=False) en vez de repetir el lookup.
    ctx.update({k: v for k, v in territorio.items() if k != "alternativas_juzgado"})
    ctx["alternativas_juzgado"] = territorio.get("alternativas_juzgado") or []

    departamento = territorio.get("departamento_juzgado")
    ctx["notificacion_secretaria_salud"] = (
        f"Secretaría de Salud de {departamento}."
        if departamento else "Secretaría de Salud Departamental."
    )

    if territorio.get("requiere_revision_juzgado"):
        revisiones.append(
            f"No se pudo confirmar el juzgado de «{ciudad}»: el documento va "
            f"dirigido al juez de reparto.")

    # ── el menor ─────────────────────────────────────────────────────────
    if tipo == "tutela_menor":
        edad = solo_digitos(datos.get("edad_menor"))
        letras = numero_a_letras(edad)

        if letras is None:
            revisiones.append("No entendí la edad del menor; revísela antes de radicar.")
            letras = str(datos.get("edad_menor") or "").strip()
            edad = edad or letras

        ctx.update({
            "nombre_menor": str(datos.get("nombre_menor") or "").strip(),
            "registro_civil_menor": str(datos.get("registro_civil_menor") or "").strip(),
            "edad_menor_numero": edad,
            "edad_menor_texto": letras,
            "fecha_orden": str(datos.get("fecha_orden") or "").strip(),
        })

    # ── el adulto agenciado ──────────────────────────────────────────────
    if tipo in {"tutela_agente", "tutela_propia"}:
        fecha = datos.get("fecha_orden")
        if partida := partir_fecha(fecha):
            ctx["dia_orden"], ctx["mes_orden"] = partida
        else:
            ctx["dia_orden"] = str(fecha or "").strip()
            ctx["mes_orden"] = "la fecha indicada"
            revisiones.append(
                "No pude separar día y mes de la fecha de la orden médica; "
                "corríjala en el documento antes de radicar.")

    if tipo == "tutela_agente":
        ctx.update({
            "nombre_agenciado": str(datos.get("nombre_agenciado") or "").strip(),
            "cedula_agenciado": str(datos.get("cedula_agenciado") or "").strip(),
            "lugar_expedicion_agenciado":
                str(datos.get("lugar_expedicion_agenciado") or "").strip(),
            "edad_agenciado": solo_digitos(datos.get("edad_agenciado"))
                              or str(datos.get("edad_agenciado") or "").strip(),
            "relacion_agente_agenciado":
                str(datos.get("relacion_agente_agenciado") or "").strip(),
        })

    ctx["_revisiones"] = revisiones
    return ctx
