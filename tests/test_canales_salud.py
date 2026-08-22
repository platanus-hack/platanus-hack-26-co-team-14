from datos.canales_salud import EPS_VIGENTES, reconocer_eps, resolver_canal
from extraccion import extraer
from tests.doble_claude import ClaudeDoble


def test_catalogo_contiene_las_28_eps_del_listado_oficial():
    assert len(EPS_VIGENTES) == 28
    assert reconocer_eps("Compensar") == "Compensar EPS"
    assert reconocer_eps("EPS S.O.S.") == "Servicio Occidental de Salud EPS SOS"
    assert reconocer_eps("AIC EPSI") == "Asociación Indígena del Cauca EPSI"


def test_eps_conocida_sin_url_no_inventa_canal():
    resultado = resolver_canal("Capital Salud")
    assert resultado["estado"] == "eps_reconocida_sin_canal"
    assert resultado["canal"] is None


def test_respuesta_compensar_gana_a_una_extraccion_incierta():
    doble = ClaudeDoble(inicial={})
    resultado = extraer("Compensar", esperando="eps", client=doble)
    assert resultado["slots"]["eps"] == "Compensar EPS"
