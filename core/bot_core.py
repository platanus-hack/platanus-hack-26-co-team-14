"""
Orquestador principal del caso.

Kapso habla con este módulo.
"""

from core.estado import (
    actualizar_desde_extraccion,
    establecer_ruta,
    marcar_pregunta,
    registrar_mensaje,
)

from extraccion import extraer
from core.preguntas import siguiente_accion


def procesar_texto(caso: dict, texto: str, client=None):
    """
    Procesa un mensaje del usuario y devuelve:

    {
        "caso": ...,
        "respuesta": ...,
        "accion": ...
    }
    """

    caso = registrar_mensaje(
        caso,
        rol="usuario",
        texto=texto,
    )

    resultado = extraer(
        texto,
        esperando=caso.get("esperando"),
        client=client,
    )

    caso = actualizar_desde_extraccion(
        caso,
        resultado,
    )

    accion = siguiente_accion(caso)

    # La ruta quedó resuelta.
    if accion["accion"] == "ruta_resuelta":

        caso = establecer_ruta(
            caso,
            accion["ruta"],
        )

        # Recalcular inmediatamente.
        accion = siguiente_accion(caso)

    # Hay algo que preguntarle.
    if accion["accion"] == "preguntar":

        caso = marcar_pregunta(
            caso,
            accion["slot"],
        )

        return {
            "caso": caso,
            "accion": accion,
            "respuesta": accion["texto"],
        }

    # Ya tenemos todo para generar.
    if accion["accion"] == "generar_documento":

        return {
            "caso": caso,
            "accion": accion,
            "respuesta": None,
        }

    return {
        "caso": caso,
        "accion": accion,
        "respuesta": (
            "Necesito revisar un dato antes de continuar."
        ),
    }