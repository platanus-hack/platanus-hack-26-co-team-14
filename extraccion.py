"""
Haiku extrae (probabilístico) -> el código decide (determinístico).

    P(slot=1 | audio)  --umbral asimétrico-->  {0, 1, ⊥}  --f(x)-->  ruta
"""
import os
from threading import Lock
import unicodedata
from pathlib import Path
from rutas import decidir_ruta   # única fuente de verdad del enrutamiento

MODELO = "claude-haiku-4-5-20251001"
SKILL = (Path(__file__).parent / "skills/triage-extraccion/SKILL.md").read_text(encoding="utf-8")
_CLIENTE = None
_CLIENTE_LOCK = Lock()


def _cliente_compartido():
    """Conserva el pool HTTP entre turnos y evita una conexión TLS por mensaje."""
    global _CLIENTE
    if _CLIENTE is None:
        with _CLIENTE_LOCK:
            if _CLIENTE is None:
                import anthropic
                _CLIENTE = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENTE

BOOLEANOS = ["riesgo_vital", "sujeto_especial", "urgencia",
             "tutela_previa_cumplida", "termino_vencido"]
ENUM = {"solicitud_previa": ["ninguna", "verbal", "escrita"],
        # Para quién es el documento. Decide la plantilla, no la ruta.
        "paciente": ["yo", "menor", "otro"]}
TRIAGE = BOOLEANOS + list(ENUM)
TEXTO = ["nombre_completo", "cedula", "eps", "servicio_negado", "ciudad_vulneracion",
         "fecha_orden", "direccion_notificaciones", "lugar_expedicion",
         "numero_fallo", "radicado", "fecha_fallo", "juzgado_fallo",
         "puntos_incumplidos",
         # Datos que exigen las minutas (juridico/campos.py).
         "diagnostico", "hecho_vulneracion",
         "nombre_menor", "registro_civil_menor", "edad_menor",
         "nombre_agenciado", "cedula_agenciado", "lugar_expedicion_agenciado",
         "edad_agenciado", "relacion_agente_agenciado"]

# Umbrales ASIMÉTRICOS. Aceptar un "sí" es barato; aceptar un "no" es caro,
# porque un falso negativo en riesgo vital manda a PQRD a quien necesitaba tutela.
TAU_SI, TAU_NO = 0.50, 0.05
TAU_TEXTO = 0.40

# Cómo resuelve cada ⊥ (mínima pérdida esperada, no máxima verosimilitud)
RESOLUCION = {"riesgo_vital": True, "sujeto_especial": True,
              "urgencia": True, "tutela_previa_cumplida": False,
              "termino_vencido": True, "solicitud_previa": "verbal",
              # Quién es el paciente NO se resuelve por defecto: escoger mal
              # la plantilla produce un documento dirigido a otra persona.
              "paciente": None}

_campo = {
    "type": "object",
    "properties": {
        "valor": {"type": ["boolean", "string", "null"]},
        "confianza": {"type": "number", "minimum": 0, "maximum": 1},
        "evidencia": {"type": ["string", "null"],
                      "description": "Frase TEXTUAL del usuario. null si no existe."},
    },
    "required": ["valor", "confianza", "evidencia"],
}

HERRAMIENTA = {
    "name": "reportar_slots",
    "description": "Reporta cada campo con valor, confianza y evidencia textual.",
    "input_schema": {
        "type": "object",
        "properties": {k: _campo for k in TRIAGE + TEXTO},
        "required": ["tutela_previa_cumplida", "solicitud_previa"],
    },
}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def verificar_evidencia(campos: dict, texto: str):
    """
    Control de alucinación: la evidencia debe existir LITERALMENTE en el texto.
    Si no está, el valor se anula. Verificable en código, no una promesa.
    """
    fuente, limpios, descartados = _norm(texto), {}, []
    for k, c in campos.items():
        if not isinstance(c, dict):
            continue
        ev, val = c.get("evidencia"), c.get("valor")
        if val is None:
            limpios[k] = c
            continue
        if not ev or _norm(ev) not in fuente:
            descartados.append((k, val, ev))
            limpios[k] = {"valor": None, "confianza": 0.0, "evidencia": None}
        else:
            limpios[k] = c
    return limpios, descartados


def discretizar(campos: dict) -> dict:
    """{valor, confianza} -> {True, False, None} con umbrales asimétricos."""
    out = {}
    for k, c in campos.items():
        v, p = c.get("valor"), float(c.get("confianza") or 0)
        if v is None:
            out[k] = None
        elif k in ENUM:
            out[k] = v if (v in ENUM[k] and p >= TAU_SI) else None
        elif k in BOOLEANOS:
            if v is True:
                out[k] = True if p >= TAU_SI else None
            else:                       # un "no" exige mucha más certeza
                out[k] = False if p >= (1 - TAU_NO) else None
        else:
            out[k] = v if p >= TAU_TEXTO else None
    return out


def resolver(slots: dict) -> dict:
    """
    ⊥ -> el lado de menor pérdida esperada.

    OJO: esto se aplica SOLO al final, cuando ya se preguntó y la persona no supo.
    Un ⊥ recién extraído significa "hay que preguntar", NO "asumir que sí".
    Aplicarlo de entrada anula el triage: todo saldría tutela.
    """
    return {k: (RESOLUCION[k] if (k in TRIAGE and v is None
                                  and RESOLUCION.get(k) is not None) else v)
            for k, v in slots.items()}




def extraer(texto: str, esperando=None, client=None) -> dict:
    """Devuelve {slots, ruta, crudo, descartados}."""
    if client is None:
        client = _cliente_compartido()

    pista = (f"\n\nLa última pregunta que se le hizo fue sobre: {esperando}. "
             f"Es probable que su respuesta se refiera a eso." if esperando else "")

    r = client.messages.create(
        model=MODELO,
        max_tokens=1500,
        system=SKILL,
        tools=[HERRAMIENTA],
        tool_choice={"type": "tool", "name": "reportar_slots"},
        messages=[{"role": "user",
                   "content": f"Lo que dijo la persona:\n\n{texto}{pista}"}],
    )
    crudo = next(b.input for b in r.content if b.type == "tool_use")

    limpios, descartados = verificar_evidencia(crudo, texto)
    slots = discretizar(limpios)        # SIN resolver: los ⊥ se preguntan

    # Los nombres de EPS se resuelven primero contra el catálogo oficial. Una
    # respuesta corta como «Compensar» no debe perderse porque el modelo haya
    # devuelto baja confianza.
    if esperando == "eps":
        from datos.canales_salud import reconocer_eps
        if eps := reconocer_eps(texto):
            slots["eps"] = eps
            crudo["eps"] = {
                "valor": eps,
                "confianza": 1.0,
                "evidencia": texto,
            }

    return {"slots": slots, "ruta": decidir_ruta(slots),
            "crudo": crudo, "descartados": descartados}
