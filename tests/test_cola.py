from threading import Event, Lock

from puente import cola


def test_telefonos_distintos_se_procesan_en_paralelo():
    iniciaron = {"uno": Event(), "dos": Event()}
    liberar = Event()

    def trabajo(mensaje):
        iniciaron[mensaje["marca"]].set()
        liberar.wait(2)

    assert cola.encolar(trabajo, {"telefono": "571", "marca": "uno"})
    assert cola.encolar(trabajo, {"telefono": "572", "marca": "dos"})

    assert iniciaron["uno"].wait(1)
    assert iniciaron["dos"].wait(1)
    liberar.set()


def test_un_telefono_conserva_el_orden():
    terminado = Event()
    resultados = []
    bloqueo = Lock()

    def trabajo(mensaje):
        with bloqueo:
            resultados.append(mensaje["numero"])
            if len(resultados) == 3:
                terminado.set()

    for numero in (1, 2, 3):
        assert cola.encolar(trabajo, {"telefono": "573", "numero": numero})

    assert terminado.wait(2)
    assert resultados == [1, 2, 3]
