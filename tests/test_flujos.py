from core.estado import nuevo_caso
from core.bot_core import procesar_texto


class FakeExtractor:
    def __init__(self):
        self.paso = 0

    def extraer(self, texto, esperando=None, client=None):
        self.paso += 1

        if self.paso == 1:
            return {
                "slots": {
                    "tutela_previa_cumplida": None,
                    "solicitud_previa": "verbal",
                    "riesgo_vital": None,
                    "sujeto_especial": True,
                    "urgencia": True,
                    "termino_vencido": None,

                    "nombre_completo": None,
                    "cedula": None,
                    "eps": None,
                    "servicio_negado": "insulina",
                    "ciudad_vulneracion": None,
                    "fecha_orden": "antes de Semana Santa",
                    "direccion_notificaciones": None,
                    "lugar_expedicion": None,
                },

                "crudo": {
                    "solicitud_previa": {
                        "valor": "verbal",
                        "confianza": 0.90,
                        "evidencia": "llevo tres semanas yendo allá por la insulina",
                    },

                    "sujeto_especial": {
                        "valor": True,
                        "confianza": 0.95,
                        "evidencia": "tengo 78 años",
                    },

                    "urgencia": {
                        "valor": True,
                        "confianza": 0.80,
                        "evidencia": "necesito la insulina",
                    },

                    "servicio_negado": {
                        "valor": "insulina",
                        "confianza": 0.95,
                        "evidencia": "por la insulina",
                    },

                    "fecha_orden": {
                        "valor": "antes de Semana Santa",
                        "confianza": 0.80,
                        "evidencia": "antes de Semana Santa",
                    },
                },

                "ruta": None,
                "descartados": [],
            }

        if self.paso == 2:
            return {
                "slots": {
                    "tutela_previa_cumplida": False,
                    "solicitud_previa": None,
                    "riesgo_vital": None,
                    "sujeto_especial": None,
                    "urgencia": None,
                    "termino_vencido": None,
                },

                "crudo": {
                    "tutela_previa_cumplida": {
                        "valor": False,
                        "confianza": 0.99,
                        "evidencia": "no, nunca he puesto una tutela",
                    }
                },

                "ruta": None,
                "descartados": [],
            }

        raise RuntimeError("El flujo pidió más extracciones de las esperadas")


def test_flujo_insulina_termina_en_tutela(monkeypatch):
    fake = FakeExtractor()

    monkeypatch.setattr(
        "core.bot_core.extraer",
        fake.extraer,
    )

    caso = nuevo_caso()

    # Primer audio
    r1 = procesar_texto(
        caso,
        "Tengo 78 años y llevo tres semanas yendo allá por la insulina. "
        "La doctora me la mandó antes de Semana Santa.",
    )

    caso = r1["caso"]

    assert r1["accion"]["accion"] == "preguntar"
    assert r1["accion"]["slot"] == "tutela_previa_cumplida"

    # Aseguramos que conservó lo extraído del audio inicial
    assert caso["slots"]["sujeto_especial"] is True
    assert caso["slots"]["solicitud_previa"] == "verbal"
    assert caso["slots"]["urgencia"] is True

    assert caso["datos"]["servicio_negado"] == "insulina"
    assert caso["datos"]["fecha_orden"] == "antes de Semana Santa"

    # Respuesta a la pregunta dinámica
    r2 = procesar_texto(
        caso,
        "No, nunca he puesto una tutela.",
    )

    caso = r2["caso"]

    # Debe mantener el contexto previo
    assert caso["slots"]["tutela_previa_cumplida"] is False
    assert caso["slots"]["sujeto_especial"] is True
    assert caso["slots"]["solicitud_previa"] == "verbal"
    assert caso["slots"]["urgencia"] is True

    # El router ya debió decidir tutela
    assert caso["ruta"] == "tutela"
    assert caso["fase"] == "requisitos"

    # Ahora la siguiente pregunta debe ser DOCUMENTAL,
    # no otra pregunta de triage.
    assert r2["accion"]["accion"] == "preguntar"
    assert r2["accion"]["fase"] == "requisitos"
    assert r2["accion"]["slot"] == "nombre_completo"