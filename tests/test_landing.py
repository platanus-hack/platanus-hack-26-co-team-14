import pytest
from fastapi.testclient import TestClient

from app import app
from puente import config
from puente.app import _cache_numero_kapso


cliente = TestClient(app)


@pytest.fixture(autouse=True)
def limpiar_cache_numero():
    _cache_numero_kapso.update(valor="", vence=0.0)
    yield
    _cache_numero_kapso.update(valor="", vence=0.0)


def test_la_raiz_sirve_la_landing():
    respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/html")
    assert "Temis te escucha" in respuesta.text
    assert "/static/styles.css" in respuesta.text


def test_los_assets_del_frontend_se_sirven():
    respuesta = cliente.get("/static/styles.css")

    assert respuesta.status_code == 200
    assert "--orange" in respuesta.text


def test_config_publica_y_qr_comparten_el_mismo_numero(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_WHATSAPP_NUMBER", "+57 300 111 2233")
    monkeypatch.setattr(
        config,
        "WHATSAPP_START_MESSAGE",
        "Hola, necesito ayuda con mi EPS.",
    )

    publica = cliente.get("/api/public-config")
    qr = cliente.get("/qr/whatsapp.png")

    assert publica.status_code == 200
    assert publica.json()["configured"] is True
    assert publica.json()["whatsappNumber"] == "573001112233"
    assert publica.json()["whatsappUrl"].startswith("https://wa.me/573001112233?")
    assert qr.status_code == 200
    assert qr.headers["content-type"].startswith("image/png")
    assert qr.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_qr_no_inventa_un_numero_si_falta_configuracion(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_WHATSAPP_NUMBER", "")
    monkeypatch.setattr(config, "KAPSO_API_KEY", "")
    monkeypatch.setattr(config, "KAPSO_PHONE_NUMBER_ID", "")

    publica = cliente.get("/api/public-config")
    qr = cliente.get("/qr/whatsapp.png")

    assert publica.json()["configured"] is False
    assert publica.json()["whatsappUrl"] is None
    assert qr.status_code == 503


def test_descubre_el_numero_real_desde_kapso(monkeypatch):
    class RespuestaKapso:
        def raise_for_status(self):
            return None

        def json(self):
            return {"display_phone_number": "+57 310 987 6543"}

    llamadas = []

    def obtener(url, **opciones):
        llamadas.append((url, opciones))
        return RespuestaKapso()

    monkeypatch.setattr(config, "PUBLIC_WHATSAPP_NUMBER", "")
    monkeypatch.setattr(config, "KAPSO_API_KEY", "kapso-prueba")
    monkeypatch.setattr(config, "KAPSO_PHONE_NUMBER_ID", "phone-id-prueba")
    monkeypatch.setattr("puente.app.httpx.get", obtener)

    primera = cliente.get("/api/public-config")
    segunda = cliente.get("/api/public-config")

    assert primera.json()["whatsappNumber"] == "573109876543"
    assert primera.json()["whatsappUrl"].startswith("https://wa.me/573109876543?")
    assert segunda.json()["whatsappNumber"] == "573109876543"
    assert len(llamadas) == 1
    assert llamadas[0][1]["headers"] == {"X-API-Key": "kapso-prueba"}
