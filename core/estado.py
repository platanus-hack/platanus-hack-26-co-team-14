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

    # Quién es el paciente: "yo" | "menor" | "otro".
    # Decide la plantilla. No lo decide un modelo: se pregunta.
    "paciente",

    # Relato y diagnóstico, en palabras de la persona.
    "diagnostico",
    "hecho_vulneracion",

    # menor de edad agenciado
    "nombre_menor",
    "registro_civil_menor",
    "edad_menor",

    # adulto agenciado
    "nombre_agenciado",
    "cedula_agenciado",
    "lugar_expedicion_agenciado",
    "edad_agenciado",
    "relacion_agente_agenciado",

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

        # Veces consecutivas que una respuesta no llenó el dato pedido.
        # Permite cambiar de estrategia en vez de repetir como un disco rayado.
        "intentos_fallidos": {},

        # Slot al que estamos esperando respuesta.
        "esperando": None,

        # Datos derivados de lookups determinísticos.
        "normalizados": {},

        # Evita confundir inferencia con información confirmada.
        "fuente": {},

        # La conversación jurídica no empieza hasta contar con autorización
        # explícita para tratar datos de salud y demás información sensible.
        "consentimiento": {
            "otorgado": False,
            "version": None,
            "fecha": None,
            "mensaje_id": None,
            "respuesta": None,
        },
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

    # Si lo que estábamos esperando ya llegó, se deja de esperar.
    #
    # Sin esto, `esperando` se queda clavado en la primera pregunta y
    # `extraer()` le sigue mandando a Haiku la pista «la última pregunta fue
    # sobre X» durante el resto de la conversación. La pista deja de ayudar y
    # empieza a estorbar: empuja a leer cada respuesta como si fuera sobre X.
    esperado = nuevo.get("esperando")
    if esperado and _tiene_valor(nuevo, esperado):
        nuevo["esperando"] = None
        nuevo.setdefault("intentos_fallidos", {}).pop(esperado, None)

    return nuevo


def _tiene_valor(caso: dict, campo: str) -> bool:
    for grupo in ("slots", "datos"):
        valor = caso.get(grupo, {}).get(campo)
        if valor is not None and valor != "":
            return True
    return False


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
