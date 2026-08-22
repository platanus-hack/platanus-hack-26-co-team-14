"""
Mapping de la plantilla:

1.-MODELO-DE-MINUTA-DE-TUTELA-MENOR-DE-EDAD-CON-MEDIDA-PROVISIONAL.docx

29 placeholders X
+
5 regiones rojas detectadas

La selección de campos es determinística.
No hay LLM en esta capa.
"""


MAPEO_TUTELA_MENOR = [
    # 001
    "nombre_agente",

    # 002
    "nombre_menor",

    # 003
    "eps",

    # 004
    "nombre_agente",

    # 005
    "cedula_agente",

    # 006
    "lugar_expedicion_agente",

    # 007
    "nombre_menor",

    # 008
    "registro_civil_menor",

    # 009
    "eps",

    # 010
    "edad_menor_texto",

    # 011
    "edad_menor_numero",

    # 012
    "eps",

    # 013
    "fecha_orden",

    # 014
    "eps",

    # 015
    "eps",

    # 016
    "servicio_urgente",

    # 017
    "eps",

    # 018
    "eps",

    # 019
    "nombre_menor",

    # 020
    "nombre_menor",

    # 021
    "diagnostico",

    # 022
    "eps",

    # 023
    "eps",

    # 024
    "servicio_urgente",

    # 025
    "notificacion_accionada",

    # 026
    "notificacion_accionante",

    # 027
    "nombre_agente",

    # 028
    "cedula_agente",

    # 029
    "lugar_expedicion_agente",
]


# ----------------------------------------------------------------
# REGIONES EDITABLES QUE NO SON XXXXX
# ----------------------------------------------------------------
#
# El inspector encontró cinco:
#
# 1. "Detallar la vulneración..."
# 2. "(ESCRIBIR LA ATENCIÓN...)"
# 3. "ASIGNAR"
# 4. "O ENTREGAR, O AUTORIZAR, O A REALIZAR…"
# 5. "; O CITA, O ENTREGA DE MEDICAMENTO según el caso."
#
# Los runs 3 y 4 juntos representan UNA alternativa de plantilla:
#
#     ASIGNAR, O ENTREGAR, O AUTORIZAR, O A REALIZAR…
#
# Por eso:
#
# run 3 -> {{accion_servicio}}
# run 4 -> desaparece
#


REEMPLAZOS_TEXTO_TUTELA_MENOR = [

    {
        "nombre": "juez_destino",
        "buscar":
            "JUEZ DE TUTELA DE GIRÓN (REPARTO).",
        "reemplazar":
            "{{juez_destino}}",
    },

    {
        "nombre": "hecho_vulneracion",
        "buscar":
            "Detallar la vulneración ocasionada por la EPS "
            "al negar el suministro de los tratamientos "
            "ordenados por el médico tratante",
        "reemplazar":
            "{{hecho_vulneracion}}",
    },

    {
        "nombre":
            "eliminar_instruccion_servicio_urgente",
        "buscar":
            "(ESCRIBIR LA ATENCIÓN MEDICA MAS URGENTE "
            "QUE SE REQUIERE DE LA EPS)",
        "reemplazar": "",
    },

    {
        "nombre": "accion_servicio",
        "buscar": "ASIGNAR",
        "reemplazar":
            "{{accion_servicio}}",
    },

    {
        "nombre":
            "eliminar_alternativas_accion",
        "buscar":
            "O ENTREGAR, O AUTORIZAR, O A REALIZAR…",
        "reemplazar": "",
    },

    {
        "nombre":
            "eliminar_alternativa_tipo_servicio",
        "buscar":
            "; O CITA, O ENTREGA DE MEDICAMENTO según el caso.",
        "reemplazar": "",
    },
]