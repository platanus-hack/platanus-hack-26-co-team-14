"""
Planificador determinístico de preguntas.

Decide QUÉ información pedir.
No decide la ruta jurídica.
No llama modelos.
"""

from rutas import (
    decidir_ruta,
    suficiencia,
    ESCRITA,
    PROTECTORES,
)


PREGUNTAS_TRIAGE = {

    "tutela_previa_cumplida":
        "Antes de seguir necesito confirmar algo. "
        "¿Usted ya había presentado una tutela por este mismo problema, "
        "un juez falló a su favor y aun así la EPS no cumplió?",

    "solicitud_previa":
        "¿Ya le pidió este servicio o medicamento a la EPS? "
        "Puede decirme si todavía no lo ha pedido, "
        "si lo pidió solamente de palabra, o si lo radicó por escrito.",

    "riesgo_vital":
        "¿Esta demora ha hecho que su salud empeore o considera "
        "que su salud está en riesgo?",

    "sujeto_especial":
        "Necesito confirmar si aplica alguna protección especial. "
        "¿Es adulto mayor, menor de edad, está embarazada, "
        "tiene una discapacidad o una enfermedad grave?",

    "urgencia":
        "¿Necesita que este servicio sea prestado urgentemente "
        "o considera que no puede esperar?",

    "termino_vencido":
        "¿Hace más de 15 días hábiles que presentó por escrito esa solicitud?",
}


PREGUNTAS_DATOS = {

    "nombre_completo":
        "¿Cuál es su nombre completo?",

    "cedula":
        "¿Cuál es su número de cédula? "
        "Por favor dígamelo dígito por dígito.",

    "lugar_expedicion":
        "¿En qué municipio fue expedida su cédula?",

    "eps":
        "¿Cómo se llama su EPS? Por ejemplo: Compensar, Sanitas, Nueva EPS o Sura.",

    "servicio_negado":
        "¿Qué medicamento, procedimiento, tratamiento o servicio necesita?",

    "ciudad_vulneracion":
        "¿En qué municipio está ocurriendo este problema con la EPS?",

    "direccion_notificaciones":
        "¿En qué dirección física o correo electrónico quiere recibir las notificaciones?",

    "numero_fallo":
        "¿Cuál es el número del fallo de tutela?",

    "radicado":
        "¿Cuál es el número de radicado del proceso?",

    "fecha_fallo":
        "¿En qué fecha se emitió el fallo de tutela?",

    "juzgado_fallo":
        "¿Qué juzgado profirió el fallo de tutela?",

    "puntos_incumplidos":
        "¿Qué ordenó exactamente el juez que la EPS todavía no ha cumplido?",

    # ── Datos que exigen las minutas ─────────────────────────────────────
    # Se preguntan solo cuando la plantilla escogida los necesita.
    # Quién los pide: juridico/campos.py. Quién los formula: aquí.

    "paciente":
        "¿Para quién es esta tutela? Dígame si es para usted, "
        "para un hijo o hija menor de edad, o para otra persona adulta "
        "a la que usted está ayudando.",

    "diagnostico":
        "¿Cuál es el diagnóstico o la enfermedad por la que necesita "
        "este servicio?",

    "hecho_vulneracion":
        "Cuénteme con sus palabras qué fue lo que pasó con la EPS: "
        "qué le dijeron, cuándo, y por qué no le han dado lo que necesita.",

    "fecha_orden":
        "¿En qué fecha le ordenó el médico ese servicio o medicamento?",

    "nombre_menor":
        "¿Cuál es el nombre completo del menor?",

    "registro_civil_menor":
        "¿Cuál es el número de registro civil del menor?",

    "edad_menor":
        "¿Cuántos años tiene el menor?",

    "nombre_agenciado":
        "¿Cuál es el nombre completo de la persona a la que está ayudando?",

    "cedula_agenciado":
        "¿Cuál es el número de cédula de esa persona? "
        "Por favor dígamelo dígito por dígito.",

    "lugar_expedicion_agenciado":
        "¿En qué municipio fue expedida la cédula de esa persona?",

    "edad_agenciado":
        "¿Cuántos años tiene esa persona?",

    "relacion_agente_agenciado":
        "¿Qué es esa persona suya? Por ejemplo: madre, padre, esposo, "
        "hermana, vecino.",
}


def slots_triage_relevantes(s: dict) -> list[str]:
    """
    Retorna únicamente slots desconocidos que todavía pueden
    afectar la decisión.
    """

    # La tutela previa tiene precedencia absoluta.
    if s.get("tutela_previa_cumplida") is None:
        return ["tutela_previa_cumplida"]

    # Si fue desacato ya no necesitamos más triage.
    if s.get("tutela_previa_cumplida") is True:
        return []

    sol = s.get("solicitud_previa")

    if sol is None:
        return ["solicitud_previa"]

    # Si nunca pidió nada, ya tenemos petición.
    if sol == "ninguna":
        return []

    # Basta UN protector verdadero para determinar tutela.
    if any(s.get(k) is True for k in PROTECTORES):
        return []

    faltan_protectores = [
        k for k in PROTECTORES
        if s.get(k) is None
    ]

    if faltan_protectores:
        return faltan_protectores

    # Si pidió solo verbalmente y no existen protectores:
    # petición.
    if sol == "verbal":
        return []

    # término solamente importa si fue escrita.
    if sol == ESCRITA and s.get("termino_vencido") is None:
        return ["termino_vencido"]

    return []


def siguiente_pregunta_triage(caso: dict):
    s = caso["slots"]

    ruta = decidir_ruta(s)

    if ruta is not None:
        return None

    relevantes = slots_triage_relevantes(s)

    if not relevantes:
        return None

    # Por ahora prioridad fija DENTRO del conjunto relevante.
    # Luego podemos sustituir esto por information gain.
    prioridad = [
        "tutela_previa_cumplida",
        "solicitud_previa",
        "riesgo_vital",
        "sujeto_especial",
        "urgencia",
        "termino_vencido",
    ]

    for slot in prioridad:
        if slot in relevantes:
            return {
                "accion": "preguntar",
                "fase": "triage",
                "slot": slot,
                "texto": PREGUNTAS_TRIAGE[slot],
            }

    return None


def siguiente_pregunta_requisitos(caso: dict):
    ruta = caso.get("ruta")

    if not ruta:
        return None

    datos_completos = {
        **caso["slots"],
        **caso["datos"],
    }

    estado = suficiencia(ruta, datos_completos)

    if estado["suficiente"]:
        return None

    for slot in estado["faltan"]:
        return {
            "accion": "preguntar",
            "fase": "requisitos",
            "slot": slot,
            "texto": PREGUNTAS_DATOS.get(
                slot,
                f"Necesito confirmar el dato: {slot}."
            ),
        }

    return None


def siguiente_accion(caso: dict):
    """
    Punto único de entrada del planificador.
    """

    if caso["fase"] == "triage":

        ruta = decidir_ruta(caso["slots"])

        if ruta is not None:
            return {
                "accion": "ruta_resuelta",
                "ruta": ruta,
            }

        pregunta = siguiente_pregunta_triage(caso)

        if pregunta:
            return pregunta

        return {
            "accion": "sin_resolver",
            "motivo": "No existe una pregunta aplicable para el estado actual.",
        }

    if caso["fase"] == "requisitos":

        pregunta = siguiente_pregunta_requisitos(caso)

        if pregunta:
            return pregunta

        return {
            "accion": "generar_documento",
            "ruta": caso["ruta"],
        }

    return {
        "accion": "esperar",
    }
