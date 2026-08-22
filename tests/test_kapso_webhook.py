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
