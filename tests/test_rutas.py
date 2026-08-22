"""
Blindaje del triage. Correr antes de cada merge:  python -m pytest tests/ -q
Si algo aquí falla, alguien rompió el enrutamiento.
"""
import sys, os
from itertools import product
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from rutas import (decidir_ruta, siguiente_slot, suficiencia,
                   NINGUNA, VERBAL, ESCRITA, PROTECTORES)

D, S = "tutela_previa_cumplida", "solicitud_previa"


def test_guarda_desacato_domina():
    assert decidir_ruta({D: True}) == "desacato"


def test_nunca_enruta_sin_guardas():
    dom = {D: [True, False, None], S: [NINGUNA, VERBAL, ESCRITA, None],
           "riesgo_vital": [True, False, None], "sujeto_especial": [True, False, None],
           "urgencia": [True, False, None], "termino_vencido": [True, False, None]}
    for c in product(*dom.values()):
        e = dict(zip(dom, c))
        if e[D] is None or (e[D] is False and e[S] is None):
            assert decidir_ruta(e) is None, e


def test_sin_solicitud_no_hay_tutela():
    """Sin hecho vulnerador no se tutela, aunque haya riesgo vital."""
    e = {D: False, S: NINGUNA, "riesgo_vital": True, "urgencia": True}
    assert decidir_ruta(e) == "peticion"


def test_verbal_con_urgencia_va_a_tutela():
    """El error caro: pedir de palabra SÍ es hecho vulnerador."""
    e = {D: False, S: VERBAL, "sujeto_especial": True}
    assert decidir_ruta(e) == "tutela"


def test_verbal_sin_urgencia_va_a_peticion():
    """Sin urgencia y sin prueba: primero se crea la constancia."""
    e = {D: False, S: VERBAL, **{k: False for k in PROTECTORES}}
    assert decidir_ruta(e) == "peticion"


def test_termino_no_vencido_espera():
    e = {D: False, S: ESCRITA, **{k: False for k in PROTECTORES},
         "termino_vencido": False}
    assert decidir_ruta(e) == "esperar"


def test_urgencia_ignora_el_termino():
    """Con riesgo vital no se espera término: SU-508/2020."""
    e = {D: False, S: ESCRITA, "riesgo_vital": True, "termino_vencido": False}
    assert decidir_ruta(e) == "tutela"


def test_monotonia():
    """Agregar evidencia protectora nunca degrada la ruta."""
    orden = {"esperar": 0, "pqrd": 1, "peticion": 1, "tutela": 2, "desacato": 3}
    base = {D: False, S: ESCRITA, "termino_vencido": True,
            **{k: False for k in PROTECTORES}}
    for k in PROTECTORES:
        sub = dict(base, **{k: True})
        assert orden[decidir_ruta(sub)] >= orden[decidir_ruta(base)]


def test_pqrd_es_el_camino_mas_estrecho():
    """Solo se llega a PQRD negando todo explícitamente."""
    dom = {D: [True, False, None], S: [NINGUNA, VERBAL, ESCRITA, None],
           "riesgo_vital": [True, False, None], "sujeto_especial": [True, False, None],
           "urgencia": [True, False, None], "termino_vencido": [True, False, None]}
    n = sum(1 for c in product(*dom.values())
            if decidir_ruta(dict(zip(dom, c))) == "pqrd")
    assert n == 1


def test_ruta_y_pregunta_son_excluyentes():
    dom = {D: [True, False, None], S: [NINGUNA, VERBAL, ESCRITA, None],
           "riesgo_vital": [True, False, None], "sujeto_especial": [True, False, None],
           "urgencia": [True, False, None], "termino_vencido": [True, False, None]}
    for c in product(*dom.values()):
        e = dict(zip(dom, c))
        assert (decidir_ruta(e) is None) != (siguiente_slot(e) is None) or \
               decidir_ruta(e) is not None


def test_suficiencia_peticion_pide_menos_que_tutela():
    datos = {"nombre_completo": "Ana", "cedula": "26123456", "eps": "Nueva EPS",
             "servicio_negado": "insulina", "direccion_notificaciones": "Calle 5"}
    assert suficiencia("peticion", datos)["suficiente"] is True
    assert suficiencia("tutela", datos)["suficiente"] is False