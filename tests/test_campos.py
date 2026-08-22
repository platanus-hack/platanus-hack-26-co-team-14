"""
El traductor entre el caso y las minutas.

Todo lo de aquí es determinístico: mismas entradas, mismas salidas, siempre.
Si algo de esto empieza a depender de un modelo, el proyecto pierde su
argumento y estas pruebas se ponen rojas.
"""

from __future__ import annotations

import re

import pytest
from docx import Document

from juridico import campos
from juridico.render import PLANTILLAS, PATRON_CAMPO, iterar_parrafos


# ============================================================
# QUÉ MINUTA
# ============================================================

@pytest.mark.parametrize("datos, esperado", [
    ({"paciente": "menor"}, "tutela_menor"),
    ({"paciente": "otro"}, "tutela_agente"),
    ({"paciente": "yo"}, campos.SIN_PLANTILLA),
    ({"nombre_menor": "Sara"}, "tutela_menor"),
    ({"nombre_agenciado": "Rosa"}, "tutela_agente"),
    ({}, None),
])
def test_tipo_documento(datos, esperado):
    assert campos.tipo_documento(datos) == esperado


# ============================================================
# NÚMEROS Y FECHAS
# ============================================================

@pytest.mark.parametrize("numero, letras", [
    (0, "cero"), (8, "ocho"), (15, "quince"), (21, "veintiuno"),
    (30, "treinta"), (78, "setenta y ocho"), (100, "cien"), (105, "ciento cinco"),
])
def test_numero_a_letras(numero, letras):
    assert campos.numero_a_letras(numero) == letras


@pytest.mark.parametrize("basura", ["", None, "muchos", 500, -3])
def test_numero_a_letras_no_adivina(basura):
    assert campos.numero_a_letras(basura) is None


def test_edad_dicha_en_voz_alta():
    assert campos.solo_digitos("78 años") == "78"
    assert campos.solo_digitos("tiene como 8") == "8"


@pytest.mark.parametrize("dicho, esperado", [
    ("12 de marzo", ("12", "marzo")),
    ("12/03/2025", ("12", "marzo")),
    ("3-7-24", ("3", "julio")),
    ("marzo 12", ("12", "marzo")),
    ("el 5 de setiembre", ("5", "septiembre")),
])
def test_partir_fecha(dicho, esperado):
    assert campos.partir_fecha(dicho) == esperado


@pytest.mark.parametrize("dicho", [
    "antes de Semana Santa", "hace como un mes", "", None,
])
def test_lo_que_no_es_una_fecha_no_se_convierte_en_una(dicho):
    assert campos.partir_fecha(dicho) is None


# ============================================================
# LO QUE FALTA
# ============================================================

def test_faltantes_nombra_lo_que_falta():
    faltan = campos.faltantes("tutela_menor", {"nombre_completo": "Ana",
                                               "cedula": "  "})
    assert "nombre_completo" not in faltan
    assert "cedula" in faltan          # espacios no son un dato
    assert "nombre_menor" in faltan


# ============================================================
# EL CONTEXTO CUBRE LA PLANTILLA
# ============================================================

CASO_MENOR = {
    "paciente": "menor",
    "nombre_completo": "Ana Mosquera",
    "cedula": "26485912",
    "lugar_expedicion": "Quibdó",
    "nombre_menor": "Sara Mosquera",
    "registro_civil_menor": "1098234567",
    "edad_menor": "8",
    "eps": "sura",
    "diagnostico": "leucemia",
    "servicio_negado": "el medicamento",
    "fecha_orden": "12 de marzo",
    "hecho_vulneracion": "me dicen que vuelva mañana",
    "ciudad_vulneracion": "Quibdó",
    "direccion_notificaciones": "Calle 5 número 3-20",
}

CASO_AGENTE = {
    **CASO_MENOR,
    "paciente": "otro",
    "nombre_agenciado": "Rosa Palacios",
    "cedula_agenciado": "24681012",
    "lugar_expedicion_agenciado": "Quibdó",
    "edad_agenciado": "82",
    "relacion_agente_agenciado": "madre",
}


@pytest.mark.parametrize("tipo, caso", [
    ("tutela_menor", CASO_MENOR),
    ("tutela_agente", CASO_AGENTE),
])
def test_el_contexto_llena_todos_los_placeholders(tipo, caso):
    """La prueba que importa: que no falte ni un hueco de la minuta.

    Si alguien añade un {{campo}} a una plantilla y no lo mapea aquí, esto se
    entera antes de que se entere una usuaria."""
    doc = Document(PLANTILLAS[tipo])
    huecos = {m.group(1)
              for parrafo in iterar_parrafos(doc)
              for m in PATRON_CAMPO.finditer(parrafo.text)}

    contexto = campos.contexto(tipo, caso, telefono="573001112233")
    contexto.pop("_revisiones")

    sin_llenar = {h for h in huecos
                  if not str(contexto.get(h) or "").strip()}

    assert not sin_llenar, f"la minuta {tipo} pide campos sin mapear: {sin_llenar}"


def test_no_se_inventa_un_juzgado():
    """Un municipio que no está en la tabla no produce un juzgado inventado."""
    contexto = campos.contexto(
        "tutela_menor",
        {**CASO_MENOR, "ciudad_vulneracion": "Villa Inexistente del Norte"},
        telefono="573001112233")

    assert "REPARTO" in contexto["juez_destino"]
    assert contexto["email_juzgado"] is None
    assert any("juzgado" in r.lower() for r in contexto["_revisiones"])


def test_una_fecha_que_no_se_entiende_se_avisa():
    contexto = campos.contexto(
        "tutela_agente",
        {**CASO_AGENTE, "fecha_orden": "antes de Semana Santa"},
        telefono="573001112233")

    assert contexto["dia_orden"] == "antes de Semana Santa"
    assert any("fecha" in r.lower() for r in contexto["_revisiones"])


def test_el_telefono_entra_en_las_notificaciones():
    contexto = campos.contexto("tutela_menor", CASO_MENOR, telefono="573001112233")
    assert "573001112233" in contexto["notificacion_accionante"]
    assert "Ana Mosquera" in contexto["notificacion_accionante"]
