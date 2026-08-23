from puente import kapso
from puente.kapso import extraer_mensajes, leer_mensaje


def test_normaliza_payload_v2_con_telefono_en_extension_kapso():
    payload = {
        "message": {
            "id": "wamid.123",
            "type": "text",
            "text": {"body": "Hola"},
            "kapso": {
                "direction": "inbound",
                "phone_number": "+573001112233",
                "phone_number_id": "business-number-id",
            },
        },
        "conversation": {"id": "conv_123"},
    }

    mensaje = leer_mensaje(payload)

    assert mensaje["telefono"] == "+573001112233"
    assert mensaje["texto"] == "Hola"
    assert mensaje["direccion"] == "inbound"


def test_desenvuelve_payload_sin_buffering_con_data():
    payload = {
        "event": "whatsapp.message.received",
        "data": {
            "message": {
                "id": "wamid.456",
                "type": "text",
                "text": {"body": "Buenas"},
                "kapso": {
                    "direction": "inbound",
                    "phone_number": "+573004445566",
                },
            }
        },
    }

    eventos = extraer_mensajes(payload)

    assert len(eventos) == 1
    assert leer_mensaje(eventos[0])["telefono"] == "+573004445566"


def test_encuentra_telefono_en_contacto_de_una_variante_del_payload():
    payload = {
        "message": {
            "id": "wamid.789",
            "type": "text",
            "text": {"body": "Hola"},
            "kapso": {"direction": "inbound"},
        },
        "contact": {"wa_id": "573009998877"},
        "phone_number_id": "business-number-id",
    }

    assert leer_mensaje(payload)["telefono"] == "573009998877"


def test_normaliza_respuesta_de_boton_de_consentimiento():
    payload = {
        "message": {
            "id": "wamid.boton",
            "from_user_id": "573009998877",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {
                    "id": "consentimiento_autorizar",
                    "title": "Autorizar",
                },
            },
            "kapso": {"direction": "inbound"},
        }
    }

    mensaje = leer_mensaje(payload)

    assert mensaje["boton_id"] == "consentimiento_autorizar"
    assert mensaje["texto"] == "Autorizar"


def test_envia_botones_interactivos(monkeypatch):
    enviados = []
    monkeypatch.setattr(kapso, "_enviar", lambda cuerpo: enviados.append(cuerpo) or {})

    kapso.enviar_botones(
        "573001112233",
        "¿Autoriza?",
        [
            {"id": "consentimiento_autorizar", "titulo": "Autorizar"},
            {"id": "consentimiento_rechazar", "titulo": "No autorizar"},
        ],
    )

    cuerpo = enviados[0]
    assert cuerpo["type"] == "interactive"
    assert cuerpo["interactive"]["type"] == "button"
    assert cuerpo["interactive"]["action"]["buttons"][0]["reply"]["id"] == (
        "consentimiento_autorizar")


def test_no_confunde_bsuid_con_numero_de_telefono():
    payload = {
        "message": {
            "id": "wamid.bsuid",
            "type": "text",
            "text": {"body": "Hola"},
            "from_user_id": "CO.2229571711221402",
            "kapso": {"direction": "inbound"},
        },
        "conversation": {
            "id": "conversation-123",
            "phone_number": None,
            "business_scoped_user_id": "CO.2229571711221402",
        },
    }

    mensaje = leer_mensaje(payload)

    assert mensaje["telefono"] is None
    assert mensaje["identidad_usuario"] == "CO.2229571711221402"
    assert mensaje["conversation_id"] == "conversation-123"
