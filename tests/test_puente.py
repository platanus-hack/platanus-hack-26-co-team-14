"""
El puente y el cerebro, enchufados.

Lo que se comprueba aquí no es la lógica jurídica —eso es test_integracion—
sino que el cable existe: que un evento de Kapso entra por el webhook, sale
por el cerebro y vuelve convertido en mensajes de WhatsApp.

Nada de esto toca la red: Kapso y ElevenLabs están sustituidos.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app as aplicacion
from puente import backend, cola, config, kapso
from puente.app import _vistos

EVENTO_TEXTO = {
    "message": {
        "id": "wamid.PRUEBA1",
        "type": "text",
        "text": {"body": "la eps no me ha dado el medicamento"},
        "timestamp": "1730093100",
        "kapso": {"direction": "inbound"},
    },
    "conversation": {"phone_number": "573001112233"},
}


@pytest.fixture
def cliente():
    return TestClient(aplicacion.app)


@pytest.fixture(autouse=True)
def limpiar_idempotencia():
    _vistos.clear()
    yield
    _vistos.clear()


@pytest.fixture
def enviados(monkeypatch):
    """Intercepta todo lo que el puente intentaría mandar por WhatsApp."""
    registro = []

    monkeypatch.setattr(
        kapso,
        "marcar_leido_escribiendo",
        lambda mid: registro.append(("escribiendo", mid)),
    )

    monkeypatch.setattr(kapso, "enviar_texto",
                        lambda tel, txt: registro.append(("texto", tel, txt)))
    monkeypatch.setattr(kapso, "subir_media",
                        lambda *a, **k: "media-de-mentira")
    monkeypatch.setattr(kapso, "enviar_audio_por_id",
                        lambda tel, mid, **k: registro.append(("audio", tel, mid)))
    monkeypatch.setattr(kapso, "enviar_documento_por_id",
                        lambda tel, mid, nom, desc="": registro.append(
                            ("documento", tel, nom)))
    return registro


# ============================================================
# EL CABLE
# ============================================================

def test_webhook_contesta_rapido_y_procesa_despues(cliente, enviados, monkeypatch):
    """Kapso corta a los 10 s. El webhook contesta y el trabajo va aparte."""
    monkeypatch.setattr(backend, "_local", lambda mensaje: [
        {"tipo": "texto", "texto": f"recibí: {mensaje['texto']}"},
    ])

    r = cliente.post("/webhooks/whatsapp", json=EVENTO_TEXTO,
                     headers={"X-Webhook-Event": "message.received"})

    assert r.status_code == 200
    assert r.json()["encolados"] == 1
    assert ("texto", "573001112233",
            "recibí: la eps no me ha dado el medicamento") in enviados
    assert ("escribiendo", "wamid.PRUEBA1") in enviados


def test_la_ruta_vieja_de_kapso_sigue_viva(cliente, enviados, monkeypatch):
    monkeypatch.setattr(backend, "_local", lambda m: [{"tipo": "texto", "texto": "ok"}])

    r = cliente.post("/webhooks/kapso", json=EVENTO_TEXTO,
                     headers={"X-Webhook-Event": "message.received"})

    assert r.status_code == 200
    assert ("texto", "573001112233", "ok") in enviados


def test_el_documento_se_sube_en_vez_de_publicarse(cliente, enviados, monkeypatch,
                                                   tmp_path):
    """En serverless no hay disco que sobreviva: el archivo va a Kapso."""
    archivo = tmp_path / "tutela.docx"
    archivo.write_bytes(b"PK\x03\x04 documento de mentira")

    monkeypatch.setattr(backend, "_local", lambda m: [
        {"tipo": "documento", "archivo": str(archivo), "nombre": "tutela.docx"},
    ])

    cliente.post("/webhooks/whatsapp", json=EVENTO_TEXTO,
                 headers={"X-Webhook-Event": "message.received"})

    assert ("documento", "573001112233", "tutela.docx") in enviados


def test_los_reintentos_de_kapso_no_duplican(cliente, enviados, monkeypatch):
    monkeypatch.setattr(backend, "_local", lambda m: [{"tipo": "texto", "texto": "ok"}])
    cabeceras = {"X-Webhook-Event": "message.received",
                 "X-Idempotency-Key": "clave-repetida"}

    cliente.post("/webhooks/whatsapp", json=EVENTO_TEXTO, headers=cabeceras)
    segunda = cliente.post("/webhooks/whatsapp", json=EVENTO_TEXTO, headers=cabeceras)

    assert segunda.json()["nota"] == "duplicado"
    # Primer evento: indicador + texto. El reintento no produce nada nuevo.
    assert len(enviados) == 2


def test_los_mensajes_que_manda_el_bot_no_se_contestan(cliente, enviados, monkeypatch):
    monkeypatch.setattr(backend, "_local", lambda m: [{"tipo": "texto", "texto": "eco"}])

    saliente = {**EVENTO_TEXTO,
                "message": {**EVENTO_TEXTO["message"],
                            "kapso": {"direction": "outbound"}}}

    r = cliente.post("/webhooks/whatsapp", json=saliente,
                     headers={"X-Webhook-Event": "message.received"})

    assert r.json()["encolados"] == 0
    assert enviados == []


def test_un_mismo_id_no_activa_dos_veces_el_bot(cliente, enviados, monkeypatch):
    monkeypatch.setattr(backend, "_local", lambda m: [{"tipo": "texto", "texto": "ok"}])

    primera = cliente.post("/webhooks/whatsapp", json=EVENTO_TEXTO,
                           headers={"X-Webhook-Event": "message.received"})
    segunda = cliente.post("/webhooks/whatsapp", json=EVENTO_TEXTO,
                           headers={"X-Webhook-Event": "message.received"})

    assert primera.json()["encolados"] == 1
    assert segunda.json()["encolados"] == 0
    assert [e for e in enviados if e[0] == "texto"] == [
        ("texto", "573001112233", "ok")
    ]


def test_evento_sin_mensaje_real_se_ignora(cliente, enviados):
    estado = {
        "message": {"id": "wamid.ESTADO", "type": "audio",
                    "kapso": {"direction": "outbound"}},
        "conversation": {"phone_number": "573001112233"},
    }

    respuesta = cliente.post(
        "/webhooks/whatsapp", json=estado,
        headers={"X-Webhook-Event": "whatsapp.message.sent"})

    assert respuesta.json()["encolados"] == 0
    assert enviados == []


def test_identifica_usuario_en_nuevo_payload_de_kapso():
    evento = {
        "message": {
            "id": "wamid.NUEVO",
            "type": "text",
            "text": {"body": "Hola"},
            "from_user_id": "CO.2229571711221402",
            "kapso": {"direction": "inbound"},
        },
        "conversation": {"business_scoped_user_id": "987654321012345"},
        "phone_number_id": "111111111111111",
    }

    normalizado = kapso.leer_mensaje(evento)

    assert normalizado["telefono"] is None
    assert normalizado["identidad_usuario"] == "CO.2229571711221402"


def test_conexion_rapida_confirma_sin_esperar(cliente, monkeypatch):
    recibido = []
    monkeypatch.setattr(
        cola, "encolar",
        lambda funcion, mensaje: recibido.append(mensaje) is None or True,
    )

    respuesta = cliente.post(
        "/api/conexion-rapida",
        json={"telefono": "573001112233", "texto": "Hola"},
        headers={"Authorization": f"Bearer {config.API_TOKEN}"},
    )

    assert respuesta.status_code == 202
    assert respuesta.json()["encolado"] is True
    assert recibido[0]["texto"] == "Hola"


# ============================================================
# EL CONTRATO, POR HTTP
# ============================================================

def test_mensaje_devuelve_la_lista_de_acciones(cliente, monkeypatch):
    monkeypatch.setattr("canal.cerebro.procesar_turno",
                        lambda tel, txt, **k: [{"tipo": "texto", "texto": "hecho"}])

    r = cliente.post("/mensaje", json={"telefono": "573001112233",
                                       "texto": "hola", "tipo": "text"})

    assert r.status_code == 200
    assert r.json() == {"responder": [{"tipo": "texto", "texto": "hecho"}]}


def test_mensaje_sin_telefono_se_rechaza(cliente):
    r = cliente.post("/mensaje", json={"texto": "hola"})
    assert r.status_code == 400


# ============================================================
# DIAGNÓSTICO
# ============================================================

def test_salud_dice_que_el_cerebro_esta_conectado(cliente):
    assert cliente.get("/salud").json()["backend_modo"] == "en_proceso"


def test_health_lista_las_plantillas_disponibles(cliente):
    cuerpo = cliente.get("/health").json()
    assert cuerpo["ok"] is True
    assert "tutela_menor" in cuerpo["plantillas"]
