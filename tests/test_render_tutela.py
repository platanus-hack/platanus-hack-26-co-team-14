from juridico.render import (
    renderizar_documento,
)


datos = {
    "nombre_agente":
        "María Pérez",

    "nombre_menor":
        "Juan Pérez",

    "eps":
        "Nueva EPS",

    "cedula_agente":
        "1234567890",

    "lugar_expedicion_agente":
        "Bogotá",

    "registro_civil_menor":
        "123456789",

    "edad_menor_texto":
        "diez",

    "edad_menor_numero":
        "10",

    "fecha_orden":
        "15 de agosto de 2026",

    "diagnostico":
        "diabetes mellitus tipo 1",

    "servicio_urgente":
        "entregar la insulina prescrita",

    "accion_servicio":
        "ENTREGAR",

    "hecho_vulneracion":
        (
            "La EPS no ha autorizado la entrega "
            "de la insulina prescrita por el "
            "médico tratante, generando una "
            "interrupción en el tratamiento."
        ),

    "ciudad_vulneracion":
        "Puerto Nariño",

    "departamento_vulneracion":
        "Amazonas",

    "notificacion_accionada":
        "Nueva EPS",

    "notificacion_accionante":
        "maria@example.com",
}


resultado = renderizar_documento(
    tipo="tutela_menor",

    datos=datos,

    salida=(
        "salidas/"
        "tutela_menor_puerto_narino.docx"
    ),
)


print()
print("DOCUMENTO GENERADO")
print()

for clave, valor in resultado.items():
    print(
        f"{clave}: {valor}"
    )