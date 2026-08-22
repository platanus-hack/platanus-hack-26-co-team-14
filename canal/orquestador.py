"""
Adaptador entre canales externos y el core.

WhatsApp/Kapso entrega texto.
Este módulo ejecuta un turno del sistema.
"""

from canal.sesiones import (
    obtener_sesion,
    guardar_sesion,
)

from datos.canales_salud import (
    resolver_canal,
)

from juridico.render import (
    renderizar_documento,
)


def procesar_turno_core(
    usuario_id: str,
    texto: str,
):
    """
    Esta función será el único puente hacia bot_core.

    Ajustaremos la llamada exacta según la firma que ya
    tengas actualmente en core/bot_core.py.
    """

    from core.bot_core import procesar_mensaje

    estado = obtener_sesion(
        usuario_id
    )

    resultado = procesar_mensaje(
        estado=estado,
        texto=texto,
    )

    nuevo_estado = resultado[
        "estado"
    ]

    guardar_sesion(
        usuario_id,
        nuevo_estado,
    )

    return resultado

def construir_respuesta_final(
    usuario_id: str,
    resultado: dict,
):
    """
    Convierte el resultado interno del core
    en una acción para el canal.
    """

    estado = resultado[
        "estado"
    ]

    # --------------------------------------------------------
    # Todavía falta información
    # --------------------------------------------------------

    pregunta = resultado.get(
        "pregunta"
    )

    if pregunta:
        return {
            "tipo": "pregunta",
            "texto": pregunta,
        }

    ruta = estado.get(
        "ruta"
    )

    datos = estado.get(
        "datos",
        {}
    )

    # --------------------------------------------------------
    # TUTELA
    # --------------------------------------------------------

    if ruta == "tutela":

        tipo_tutela = decidir_tipo_tutela(
            datos
        )

        archivo = (
            f"salidas/"
            f"{usuario_id}_tutela.docx"
        )

        render = renderizar_documento(
            tipo=tipo_tutela,
            datos=datos,
            salida=archivo,
        )

        return {
            "tipo": "documento",

            "ruta": "tutela",

            "texto": (
                "Ya tengo la información necesaria "
                "para preparar tu acción de tutela."
            ),

            "archivo":
                render["archivo"],

            "juez_destino":
                render["juez_destino"],

            "email_juzgado":
                render["email_juzgado"],

            "dane_juzgado":
                render["dane_juzgado"],
        }

    # --------------------------------------------------------
    # PQR / PETICIÓN
    # --------------------------------------------------------

    if ruta in {
        "pqrd",
        "peticion",
    }:

        entidad = (
            datos.get("eps")
            or datos.get("ips")
        )

        canal = resolver_canal(
            entidad
        )

        if not canal.get("canal"):

            return {
                "tipo": "instruccion",
                "ruta": ruta,
                "texto": (
                    "Ya determiné la ruta, pero no tengo "
                    "un canal verificado para esa entidad. "
                    "No voy a inventar uno."
                ),
            }

        info = canal["canal"]

        return {
            "tipo": "canal_radicar",

            "ruta":
                ruta,

            "entidad":
                info["nombre"],

            "url":
                info["url"],

            "texto": (
                f"Para {info['nombre']} puedes usar "
                "su canal de atención y radicación."
            ),
        }

    # --------------------------------------------------------
    # ESPERAR
    # --------------------------------------------------------

    if ruta == "esperar":
        return {
            "tipo": "instruccion",
            "ruta": ruta,
            "texto": (
                "La solicitud ya fue presentada y el "
                "término correspondiente todavía no "
                "aparece vencido."
            ),
        }

    # --------------------------------------------------------
    # DESACATO
    # --------------------------------------------------------

    if ruta == "desacato":
        return {
            "tipo": "pendiente_documento",
            "ruta": ruta,
            "texto": (
                "El caso corresponde a seguimiento "
                "de una tutela previa posiblemente "
                "incumplida."
            ),
        }

    return {
        "tipo": "error_controlado",
        "texto": (
            "No pude determinar una salida válida "
            "para el estado actual."
        ),
    }


def decidir_tipo_tutela(
    datos: dict,
):
    """
    La selección de plantilla también es determinística.
    """

    if datos.get(
        "nombre_menor"
    ):
        return "tutela_menor"

    if datos.get(
        "nombre_agenciado"
    ):
        return "tutela_agente"

    raise ValueError(
        "Tutela decidida pero no hay suficiente "
        "información para seleccionar plantilla."
    )