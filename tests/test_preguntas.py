from core.estado import nuevo_caso
from core.preguntas import siguiente_accion


def test_insulina_senora_mayor():
    caso = nuevo_caso()

    caso["slots"].update({
        "tutela_previa_cumplida": None,
        "solicitud_previa": "verbal",
        "riesgo_vital": None,
        "sujeto_especial": True,
        "urgencia": True,
        "termino_vencido": None,
    })

    r = siguiente_accion(caso)

    assert r["accion"] == "preguntar"
    assert r["slot"] == "tutela_previa_cumplida"


def test_insulina_sin_tutela_previa():
    caso = nuevo_caso()

    caso["slots"].update({
        "tutela_previa_cumplida": False,
        "solicitud_previa": "verbal",
        "riesgo_vital": None,
        "sujeto_especial": True,
        "urgencia": True,
        "termino_vencido": None,
    })

    r = siguiente_accion(caso)

    assert r["accion"] == "ruta_resuelta"
    assert r["ruta"] == "tutela"


def test_tutela_previa_incumplida():
    caso = nuevo_caso()

    caso["slots"]["tutela_previa_cumplida"] = True

    r = siguiente_accion(caso)

    assert r["accion"] == "ruta_resuelta"
    assert r["ruta"] == "desacato"


def test_nunca_solicito():
    caso = nuevo_caso()

    caso["slots"].update({
        "tutela_previa_cumplida": False,
        "solicitud_previa": "ninguna",
    })

    r = siguiente_accion(caso)

    assert r["accion"] == "ruta_resuelta"
    assert r["ruta"] == "peticion"


def test_escrita_sin_protectores_pregunta_termino():
    caso = nuevo_caso()

    caso["slots"].update({
        "tutela_previa_cumplida": False,
        "solicitud_previa": "escrita",
        "riesgo_vital": False,
        "sujeto_especial": False,
        "urgencia": False,
        "termino_vencido": None,
    })

    r = siguiente_accion(caso)

    assert r["accion"] == "preguntar"
    assert r["slot"] == "termino_vencido"