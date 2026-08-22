"""
Mapping para:
2.-MODELO-DE-MINUTA-DE-TUTELA-CON-AGENTE-OFICIOSO-INTEGRAL.docx

IMPORTANTE:
- Hay exactamente 46 placeholders X.
- Cada posición de esta lista corresponde a UNA X.
- None significa: eliminar esa X porque forma parte de un
  espacio visual más grande representado por otro campo.
"""

MAPEO_TUTELA_AGENTE = [
    # 001 - 010
    "nombre_agente",
    "nombre_agenciado",
    "eps",
    "nombre_agente",
    "cedula_agente",
    "lugar_expedicion_agente",
    "nombre_agenciado",
    "cedula_agenciado",
    "lugar_expedicion_agenciado",
    "eps",

    # 011 - 016
    "nombre_agenciado",
    "edad_agenciado",
    "eps",
    "relacion_agente_agenciado",

    # Dos bloques X forman un único diagnóstico
    "diagnostico",
    None,

    # 017 - 018
    "dia_orden",
    "mes_orden",

    # 019 - 022
    # Cuatro bloques visuales forman un solo servicio ordenado
    "servicio_ordenado",
    None,
    None,
    None,

    # 023 - 024
    "relacion_agente_agenciado",
    "eps",

    # 025 - 029
    "relacion_agente_agenciado",
    "nombre_agenciado",
    "nombre_agenciado",
    "eps",
    "nombre_agenciado",

    # 030
    "eps",

    # 031 - 032
    # Pretensión principal
    "servicio_solicitado",
    None,

    # 033
    "nombre_agenciado",

    # 034 - 036
    # Medida provisional
    "servicio_urgente",
    None,
    None,

    # 037 - 039
    "nombre_agenciado",
    "nombre_agenciado",
    "nombre_agenciado",

    # 040 - 042
    "eps",
    "notificacion_eps",
    "notificacion_secretaria_salud",

    # 043
    "notificacion_accionante",

    # 044 - 046
    "nombre_agente",
    "cedula_agente",
    "lugar_expedicion_agente",
]


REEMPLAZOS_TEXTO_TUTELA_AGENTE = [

    {
        "nombre": "juez_destino",
        "buscar":
            "JUEZ PROMISCUO MUNICIPAL DE SAN JUAN GIRON (REPARTO)",
        "reemplazar":
            "{{juez_destino}}",
    },

    {
        "nombre": "hecho_vulneracion_inicio",
        "buscar":
            "SE NIEGA A (",
        "reemplazar":
            "{{hecho_vulneracion}}",
    },

    {
        "nombre":
            "eliminar_instruccion_negligencia",
        "buscar":
            "realizar una concreta descripción "
            "de la negligencia de la",
        "reemplazar":
            "",
    },
]