"""
Canales oficiales conocidos para radicación o asistencia
de solicitudes/PQRS de EPS e IPS.

No contiene lógica de triage.
No llama LLM.
"""

import re
import unicodedata
from difflib import SequenceMatcher


CANALES = {
    "sanitas": {
        "nombre": "EPS Sanitas",
        "tipo": "eps",
        "url": (
            "https://aql.epssanitas.com/"
            "AQLchat/index.html?origen=portal"
        ),
    },

    "nueva eps": {
        "nombre": "Nueva EPS",
        "tipo": "eps",
        "url": "https://www.nuevaeps.com.co/pqrs",
    },

    "compensar": {
        "nombre": "Compensar EPS",
        "tipo": "eps",
        "url": (
            "https://corporativo.compensar.com/"
            "te-escuchamos"
        ),
    },

    "sura": {
        "nombre": "EPS Sura",
        "tipo": "eps",
        "url": "https://www.epssura.com/escribenos",
    },

    "salud total": {
        "nombre": "Salud Total EPS",
        "tipo": "eps",
        "url": (
            "https://transaccional.saludtotal.com.co/"
            "TeEscuchamos/#/"
        ),
    },

    "fundacion santa fe": {
        "nombre": "Fundación Santa Fe de Bogotá",
        "tipo": "ips",
        "url": (
            "https://fundacionsantafedebogota.com/"
            "radicar-pqrsf"
        ),
    },

    "hospital pablo tobon uribe": {
        "nombre": "Hospital Pablo Tobón Uribe",
        "tipo": "ips",
        "url": (
            "https://pqr.hptu.org.co/"
            "pqrs/public/create"
        ),
    },
}


ALIASES = {
    "eps sanitas": "sanitas",
    "sanitas eps": "sanitas",

    "nuevaeps": "nueva eps",

    "compensar eps": "compensar",

    "eps sura": "sura",
    "sura eps": "sura",

    "saludtotal": "salud total",
    "salud total eps": "salud total",

    "fundacion santa fe de bogota":
        "fundacion santa fe",

    "fundacion santa fe":
        "fundacion santa fe",

    "hospital pablo tobon":
        "hospital pablo tobon uribe",

    "pablo tobon":
        "hospital pablo tobon uribe",
}


def normalizar(texto: str | None) -> str:
    if not texto:
        return ""

    texto = texto.lower().strip()

    texto = "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )

    texto = re.sub(
        r"[^a-z0-9 ]",
        " ",
        texto,
    )

    return " ".join(
        texto.split()
    )


def similitud(a: str, b: str) -> float:
    return SequenceMatcher(
        None,
        normalizar(a),
        normalizar(b),
    ).ratio()


def resolver_canal(
    entidad: str,
    umbral: float = 0.80,
):
    """
    Busca canal de EPS/IPS.

    Nunca inventa URLs.
    """

    q = normalizar(entidad)

    if not q:
        return {
            "estado": "falta_entidad",
            "canal": None,
        }

    # Exacto en alias
    if q in ALIASES:
        clave = ALIASES[q]

        return {
            "estado": "exacto",
            "canal": CANALES[clave],
        }

    # Exacto en catálogo
    if q in CANALES:
        return {
            "estado": "exacto",
            "canal": CANALES[q],
        }

    # Fuzzy
    candidatos = []

    for clave, canal in CANALES.items():

        score_clave = similitud(
            q,
            clave,
        )

        score_nombre = similitud(
            q,
            canal["nombre"],
        )

        score = max(
            score_clave,
            score_nombre,
        )

        candidatos.append(
            (
                score,
                clave,
                canal,
            )
        )

    candidatos.sort(
        reverse=True,
        key=lambda x: x[0],
    )

    mejor = candidatos[0]

    if mejor[0] < umbral:
        return {
            "estado": "no_encontrado",
            "canal": None,
        }

    return {
        "estado": "fuzzy",
        "score": mejor[0],
        "canal": mejor[2],
    }