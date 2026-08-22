"""
El recorrido entero, sin WhatsApp y sin Claude.

    texto → extracción → triage → preguntas → minuta → DOCX

Lo que se comprueba es que las piezas encajan: que las preguntas terminan,
que el documento sale, y que cuando no puede salir se dice, en vez de
entregar algo a medias.
"""

from __future__ import annotations

import re

import pytest
from docx import Document

from canal import sesiones
from canal.orquestador import procesar_turno
from tests.doble_claude import ClaudeDoble

TOPE_TURNOS = 30


def conversar(telefono: str, doble: ClaudeDoble, primer_texto: str,
              respuestas: dict[str, str] | None = None):
    """Habla hasta que el sistema deja de preguntar. Devuelve las acciones
    del último turno."""
    respuestas = respuestas or {}
    sesiones.borrar(telefono)

    acciones = procesar_turno(telefono, primer_texto, client=doble)

    for _ in range(TOPE_TURNOS):
        if any(a["tipo"] == "documento" for a in acciones):
            return acciones

        # `esperando` es el dato que el sistema acaba de pedir. Si no pidió
        # nada, la conversación se acabó.
        pendiente = sesiones.obtener(telefono).get("esperando")
        if pendiente is None or pendiente not in respuestas:
            return acciones

        acciones = procesar_turno(telefono, respuestas[pendiente], client=doble)

    pytest.fail(f"la conversación no terminó en {TOPE_TURNOS} turnos; "
                f"último slot preguntado: {doble.preguntado[-3:]}")


def textos(acciones):
    return " ".join(a.get("texto", "") for a in acciones)


# ============================================================
# TUTELA DE UN MENOR — el recorrido completo hasta el DOCX
# ============================================================

def test_tutela_de_un_menor_termina_en_documento(tmp_path):
    doble = ClaudeDoble(
        inicial={
            "tutela_previa_cumplida": False,
            "solicitud_previa": "verbal",
            "sujeto_especial": True,
            "paciente": "menor",
            "eps": "sura",
            "servicio_negado": "el medicamento",
            "diagnostico": "leucemia",
            "edad_menor": "8",
        },
        guion={
            "nombre_completo": "Ana Mosquera Palacios",
            "cedula": "26485912",
            "lugar_expedicion": "Quibdó",
            "ciudad_vulneracion": "Quibdó",
            "direccion_notificaciones": "Calle 5 número 3-20, barrio Yesquita",
            "hecho_vulneracion": ("Llevo tres semanas yendo a la farmacia y "
                                  "siempre me dicen que vuelva mañana"),
            "nombre_menor": "Sara Mosquera",
            "registro_civil_menor": "1098234567",
            "fecha_orden": "12 de marzo",
        },
    )

    acciones = conversar(
        "573001112233", doble,
        "mi hija de 8 años tiene leucemia y la eps sura no le ha entregado "
        "el medicamento, fui a la farmacia y me dijeron que volviera",
        respuestas={k: v for k, v in doble.guion.items()},
    )

    tipos = [a["tipo"] for a in acciones]
    assert "documento" in tipos, textos(acciones)
    assert "audio" in tipos, "la respuesta final tiene que ir también en voz"

    documento = next(a for a in acciones if a["tipo"] == "documento")
    ruta = documento["archivo"]

    doc = Document(ruta)
    contenido = "\n".join(p.text for p in doc.paragraphs)
    for tabla in doc.tables:
        for fila in tabla.rows:
            for celda in fila.cells:
                contenido += "\n" + celda.text

    # Ni un placeholder vivo.
    assert not re.search(r"\{\{\w+\}\}", contenido)

    # Los datos de la persona llegaron al papel.
    assert "Ana Mosquera Palacios" in contenido
    assert "Sara Mosquera" in contenido
    assert "26485912" in contenido
    assert "ocho" in contenido          # edad en letras, como pide la minuta

    # Y el caso se cerró: no guardamos datos de salud de más.
    assert sesiones.obtener("573001112233")["datos"]["cedula"] is None


# ============================================================
# LO QUE NO PUEDE SALIR, NO SALE
# ============================================================

def test_tutela_propia_no_inventa_minuta():
    """No hay plantilla para tutelar a nombre propio. Se dice, no se improvisa."""
    doble = ClaudeDoble(
        inicial={
            "tutela_previa_cumplida": False,
            "solicitud_previa": "verbal",
            "riesgo_vital": True,
            "paciente": "yo",
            "eps": "nueva eps",
            "servicio_negado": "la insulina",
        },
        guion={
            "nombre_completo": "Pedro Nel Rúa",
            "cedula": "71234567",
            "lugar_expedicion": "Medellín",
            "ciudad_vulneracion": "Medellín",
            "direccion_notificaciones": "Carrera 45 número 12-30",
            "hecho_vulneracion": "me dicen que no hay y que vuelva",
        },
    )

    acciones = conversar(
        "573004445566", doble,
        "no me han dado la insulina y cada día estoy peor, la nueva eps me "
        "dice que vuelva",
        respuestas=dict(doble.guion),
    )

    assert not any(a["tipo"] == "documento" for a in acciones)
    dicho = textos(acciones).lower()
    assert "tutela" in dicho
    assert "personería" in dicho or "defensoría" in dicho


def test_sin_pedir_nada_va_a_peticion():
    doble = ClaudeDoble(inicial={
        "tutela_previa_cumplida": False,
        "solicitud_previa": "ninguna",
        "eps": "sura",
        "servicio_negado": "una cita con el especialista",
    })

    acciones = procesar_turno(
        "573007778899",
        "apenas me la formularon y no sé ni a dónde tengo que ir",
        client=doble)
    sesiones.borrar("573007778899")

    dicho = textos(acciones).lower()
    assert "derecho de petición" in dicho
    # Sura está en el catálogo: se da el canal verificado, no uno inventado.
    assert "http" in dicho


def test_fallo_incumplido_va_a_desacato():
    doble = ClaudeDoble(inicial={"tutela_previa_cumplida": True})

    acciones = procesar_turno(
        "573001010101",
        "ya puse una tutela, el juez me dio la razón y la eps no ha cumplido",
        client=doble)
    sesiones.borrar("573001010101")

    assert "desacato" in textos(acciones).lower()


# ============================================================
# EL CANAL
# ============================================================

def test_cada_respuesta_va_escrita_y_hablada():
    doble = ClaudeDoble(inicial={})
    acciones = procesar_turno("573002020202", "buenos días", client=doble)
    sesiones.borrar("573002020202")

    assert {a["tipo"] for a in acciones} >= {"texto", "audio"}


def test_reiniciar_borra_el_caso():
    doble = ClaudeDoble(inicial={"eps": "sura"})
    procesar_turno("573003030303", "la eps sura no me atiende", client=doble)

    acciones = procesar_turno("573003030303", "empezar de nuevo", client=doble)
    assert sesiones.obtener("573003030303")["datos"]["eps"] is None
    assert "cero" in textos(acciones).lower()
    sesiones.borrar("573003030303")


def test_audio_ininteligible_no_rompe_nada():
    doble = ClaudeDoble(inicial={})
    acciones = procesar_turno("573005050505", "", client=doble)
    sesiones.borrar("573005050505")

    assert "repetir" in textos(acciones).lower()
