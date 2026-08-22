"""
Estado acumulado de un caso.

No toma decisiones jurídicas.
No llama modelos.
No genera documentos.

Su único trabajo es representar qué sabemos, de dónde salió
y en qué fase se encuentra la conversación.
"""

from copy import deepcopy
from uuid import uuid4


FASE_TRIAGE = "triage"
FASE_REQUISITOS = "requisitos"
FASE_CONFIRMACION = "confirmacion"
FASE_FINAL = "final"


TRIAGE_SLOTS = [
    "tutela_previa_cumplida",
    "solicitud_previa",
    "riesgo_vital",
    "sujeto_especial",
    "urgencia",
    "termino_vencido",
]


DATOS_CASO = [
    "nombre_completo",
    "cedula",
    "eps",
    "servicio_negado",
    "ciudad_vulneracion",
    "fecha_orden",
    "direccion_notificaciones",
    "lugar_expedicion",

    # desacato
    "numero_fallo",
    "radicado",
    "fecha_fallo",
    "juzgado_fallo",
    "puntos_incumplidos",
]


def nuevo_caso(session_id=None) -> dict:
    return {
        "id": session_id or str(uuid4()),

        "fase": FASE_TRIAGE,
        "ruta": None,

        "slots": {
            k: None
            for k in TRIAGE_SLOTS
        },

        "datos": {
            k: None
            for k in DATOS_CASO
        },

        # Evidencia textual asociada al último valor aceptado.
        "evidencia": {},

        # Confianza reportada por extracción.
        "confianza": {},

        # Historial mínimo de conversación.
        # Para hackathon puede quedarse en memoria.
        "mensajes": [],

        # Evita repetir preguntas innecesariamente.
        "preguntas_realizadas": [],

        # Slot al que estamos esperando respuesta.
        "esperando": None,

        # Datos derivados de lookups determinísticos.
        "normalizados": {},

        # Evita confundir inferencia con información confirmada.
        "fuente": {},
    }


def registrar_mensaje(caso: dict, rol: str, texto: str) -> dict:
    nuevo = deepcopy(caso)

    nuevo["mensajes"].append({
        "rol": rol,
        "texto": texto,
    })

    return nuevo


def actualizar_desde_extraccion(caso: dict, resultado: dict) -> dict:
    """
    Mezcla una nueva extracción con el estado anterior.

    Regla:
      None nuevo NO borra un valor que ya conocíamos.

    Es importante porque una respuesta corta del usuario puede hablar
    únicamente de un slot y no repetir el resto de su historia.
    """
    nuevo = deepcopy(caso)

    slots = resultado.get("slots", {})
    crudo = resultado.get("crudo", {})

    for campo, valor in slots.items():

        if valor is None:
            continue

        if campo in nuevo["slots"]:
            nuevo["slots"][campo] = valor

        elif campo in nuevo["datos"]:
            nuevo["datos"][campo] = valor

        c = crudo.get(campo, {})

        evidencia = c.get("evidencia")
        confianza = c.get("confianza")

        if evidencia:
            nuevo["evidencia"][campo] = evidencia

        if confianza is not None:
            nuevo["confianza"][campo] = confianza

        nuevo["fuente"][campo] = "usuario"

    return nuevo


def marcar_pregunta(caso: dict, slot: str) -> dict:
    nuevo = deepcopy(caso)

    nuevo["esperando"] = slot

    if slot not in nuevo["preguntas_realizadas"]:
        nuevo["preguntas_realizadas"].append(slot)

    return nuevo


def limpiar_espera(caso: dict) -> dict:
    nuevo = deepcopy(caso)
    nuevo["esperando"] = None
    return nuevo


def establecer_ruta(caso: dict, ruta: str) -> dict:
    nuevo = deepcopy(caso)

    nuevo["ruta"] = ruta

    if ruta is not None:
        nuevo["fase"] = FASE_REQUISITOS
        nuevo["esperando"] = None

    return nuevo