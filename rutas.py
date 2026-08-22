"""
Enrutamiento determinístico. Aquí no entra el modelo.

Guardas (precedencia léxica, en este orden):
  1. tutela_previa_cumplida  -> desacato
  2. solicitud_previa        -> si nunca pidió, no hay hecho vulnerador
  3. termino_vencido         -> solo si la solicitud fue escrita
Luego la disyunción de protectores.
"""
from itertools import product

NINGUNA, VERBAL, ESCRITA = "ninguna", "verbal", "escrita"

PROTECTORES = ["riesgo_vital", "sujeto_especial", "urgencia"]

PREGUNTAS = {
    "tutela_previa_cumplida":
        "¿Usted ya había puesto una tutela por esto y el juez le dio la razón, "
        "pero la EPS no ha cumplido?",
    "solicitud_previa":
        "¿Usted ya le pidió esto a la EPS? Dígame cuál de estas tres:\n"
        "1) No he pedido nada todavía\n"
        "2) Sí, pero solo de palabra (en la farmacia, en la oficina)\n"
        "3) Sí, por escrito y me quedé con la copia radicada",
    "termino_vencido":
        "¿Hace más de 15 días hábiles que radicó esa petición?",
    "riesgo_vital": "¿Su salud está en riesgo o ha empeorado por esta demora?",
    "sujeto_especial":
        "¿Usted es adulto mayor, menor de edad, está embarazada, tiene alguna "
        "discapacidad o una enfermedad grave?",
    "urgencia": "¿Necesita el servicio con urgencia?",
}


def decidir_ruta(s: dict):
    """None = falta preguntar."""
    if s.get("tutela_previa_cumplida") is True:
        return "desacato"
    if s.get("tutela_previa_cumplida") is None:
        return None

    sol = s.get("solicitud_previa")
    if sol is None:
        return None
    if sol == NINGUNA:
        return "peticion"                    # no hay hecho vulnerador todavía

    # Con urgencia, la tutela procede directa: no espera términos ni papeles.
    if any(s.get(k) is True for k in PROTECTORES):
        return "tutela"
    if any(s.get(k) is None for k in PROTECTORES):
        return None

    # Sin urgencia: la vía depende de si hay prueba y si el término maduró.
    if sol == VERBAL:
        return "peticion"                    # crear la constancia que faltará luego
    venc = s.get("termino_vencido")
    if venc is None:
        return None
    return "pqrd" if venc else "esperar"      # petición radicada aún en término


ORDEN = ["tutela_previa_cumplida", "solicitud_previa",
         "riesgo_vital", "sujeto_especial", "urgencia", "termino_vencido"]


def siguiente_slot(s: dict):
    """Qué preguntar. Salta lo que ya no cambia la ruta."""
    if decidir_ruta(s) is not None:
        return None
    for k in ORDEN:
        if s.get(k) is not None:
            continue
        if k == "termino_vencido" and s.get("solicitud_previa") != ESCRITA:
            continue
        return k
    return None


REQUISITOS = {
    "peticion": ["nombre_completo", "cedula", "eps", "servicio_negado",
                 "direccion_notificaciones"],
    "esperar":  [],
    "pqrd":     ["nombre_completo", "cedula", "eps", "servicio_negado",
                 "direccion_notificaciones", "ciudad_vulneracion"],
    "tutela":   ["nombre_completo", "cedula", "lugar_expedicion", "eps",
                 "servicio_negado", "ciudad_vulneracion",
                 "direccion_notificaciones", "tutela_previa_hechos"],
    "desacato": ["nombre_completo", "cedula", "lugar_expedicion", "eps",
                 "ciudad_vulneracion", "direccion_notificaciones",
                 "numero_fallo", "radicado", "fecha_fallo", "juzgado_fallo",
                 "puntos_incumplidos"],
}


def suficiencia(ruta, datos):
    req = REQUISITOS.get(ruta, [])
    tiene = {k for k, v in datos.items() if v not in (None, "")}
    faltan = [k for k in req if k not in tiene]
    return {"suficiente": not faltan, "faltan": faltan,
            "completitud": f"{len(req)-len(faltan)}/{len(req)}"}


if __name__ == "__main__":
    print("=== TUS TRES USUARIOS ===")
    casos = [
        ("1. mandó petición escrita, no le contestaron, término vencido, sin urgencia",
         {"tutela_previa_cumplida": False, "solicitud_previa": ESCRITA,
          "riesgo_vital": False, "sujeto_especial": False, "urgencia": False,
          "termino_vencido": True}),
        ("1b. igual pero CON riesgo vital",
         {"tutela_previa_cumplida": False, "solicitud_previa": ESCRITA,
          "riesgo_vital": True}),
        ("1c. petición radicada hace 3 días, sin urgencia",
         {"tutela_previa_cumplida": False, "solicitud_previa": ESCRITA,
          "riesgo_vital": False, "sujeto_especial": False, "urgencia": False,
          "termino_vencido": False}),
        ("2a. no sabe hacer petición PERO fue a la farmacia y le negaron (78 años)",
         {"tutela_previa_cumplida": False, "solicitud_previa": VERBAL,
          "sujeto_especial": True}),
        ("2b. no sabe hacer petición y NUNCA pidió nada",
         {"tutela_previa_cumplida": False, "solicitud_previa": NINGUNA}),
        ("2c. pidió de palabra, sin urgencia ninguna",
         {"tutela_previa_cumplida": False, "solicitud_previa": VERBAL,
          "riesgo_vital": False, "sujeto_especial": False, "urgencia": False}),
        ("3. ganó tutela y no le cumplieron",
         {"tutela_previa_cumplida": True}),
    ]
    for t, c in casos:
        r = decidir_ruta(c)
        print(f"  {t}\n      -> {r.upper() if r else 'PREGUNTAR: ' + siguiente_slot(c)}")

    dom = {"tutela_previa_cumplida": [True, False, None],
           "solicitud_previa": [NINGUNA, VERBAL, ESCRITA, None],
           "riesgo_vital": [True, False, None], "sujeto_especial": [True, False, None],
           "urgencia": [True, False, None], "termino_vencido": [True, False, None]}
    keys = list(dom)
    est = [dict(zip(keys, c)) for c in product(*dom.values())]
    from collections import Counter
    c = Counter(str(decidir_ruta(e)) for e in est)
    print(f"\n=== {len(est)} estados ===")
    for k, v in sorted(c.items()):
        print(f"  {k:<10} {v:>4}  ({100*v/len(est):.0f}%)")
    bad = [e for e in est if decidir_ruta(e) is not None and siguiente_slot(e) is not None]
    print(f"  incoherencias ruta/pregunta: {len(bad)}  (debe ser 0)")