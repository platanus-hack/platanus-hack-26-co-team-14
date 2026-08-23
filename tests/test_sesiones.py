from canal import sesiones
from core.estado import registrar_mensaje


def test_sesion_expira_tras_diez_minutos(monkeypatch, tmp_path):
    telefono = "573009999999"
    reloj = {"ahora": 1_000.0}
    monkeypatch.setattr(sesiones.time, "time", lambda: reloj["ahora"])
    monkeypatch.setattr(sesiones, "DIR_SESIONES", tmp_path)
    monkeypatch.setattr(sesiones, "HAY_DISCO", True)
    sesiones.borrar(telefono)

    caso = sesiones.obtener(telefono)
    caso = registrar_mensaje(caso, "usuario", "Mi EPS no entregó el medicamento")
    sesiones.guardar(telefono, caso)

    reloj["ahora"] += 601
    nuevo = sesiones.obtener(telefono)

    assert nuevo["mensajes"] == []
    assert nuevo["datos"]["eps"] is None
    sesiones.borrar(telefono)
