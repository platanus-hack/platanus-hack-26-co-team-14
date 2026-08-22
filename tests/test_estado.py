from core.estado import nuevo_caso, actualizar_desde_extraccion


def test_nueva_respuesta_no_borra_contexto_anterior():
    caso = nuevo_caso()

    primera = {
        "slots": {
            "sujeto_especial": True,
            "solicitud_previa": "verbal",
            "urgencia": True,
        },
        "crudo": {
            "sujeto_especial": {
                "valor": True,
                "confianza": 0.95,
                "evidencia": "tengo 78 años",
            },
            "solicitud_previa": {
                "valor": "verbal",
                "confianza": 0.90,
                "evidencia": "llevo tres semanas yendo",
            },
            "urgencia": {
                "valor": True,
                "confianza": 0.80,
                "evidencia": "necesito la insulina",
            },
        },
    }

    caso = actualizar_desde_extraccion(caso, primera)

    segunda = {
        "slots": {
            "tutela_previa_cumplida": False,
            "sujeto_especial": None,
            "solicitud_previa": None,
            "urgencia": None,
        },
        "crudo": {
            "tutela_previa_cumplida": {
                "valor": False,
                "confianza": 0.99,
                "evidencia": "no nunca",
            }
        },
    }

    caso = actualizar_desde_extraccion(caso, segunda)

    assert caso["slots"]["tutela_previa_cumplida"] is False
    assert caso["slots"]["sujeto_especial"] is True
    assert caso["slots"]["solicitud_previa"] == "verbal"
    assert caso["slots"]["urgencia"] is True