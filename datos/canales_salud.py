"""
Canales oficiales conocidos para radicación o asistencia
de solicitudes/PQRS de EPS e IPS.

No contiene lógica de triage.
No llama LLM.
"""

import re
import unicodedata
from difflib import SequenceMatcher

# Catálogo oficial de EPS vigentes, Ministerio de Salud, 5 de junio de 2025.
# Reconocer una entidad NO significa que tengamos un canal web verificado.
EPS_VIGENTES = {
    "coosalud": "Coosalud EPS-S",
    "nueva eps": "Nueva EPS",
    "mutual ser": "Mutual Ser",
    "salud mia": "Salud Mía",
    "aliansalud": "Aliansalud EPS",
    "salud total": "Salud Total EPS",
    "sanitas": "EPS Sanitas",
    "sura": "EPS Sura",
    "famisanar": "Famisanar EPS",
    "sos": "Servicio Occidental de Salud EPS SOS",
    "comfenalco valle": "Comfenalco Valle EPS",
    "compensar": "Compensar EPS",
    "epm": "Empresas Públicas de Medellín EPM",
    "ferrocarriles nacionales": "Fondo de Pasivo Social de Ferrocarriles Nacionales",
    "cajacopi": "Cajacopi Atlántico",
    "capresoca": "Capresoca EPS",
    "comfachoco": "Comfachocó",
    "comfaoriente": "Comfaoriente",
    "familiar de colombia": "EPS Familiar de Colombia",
    "asmet salud": "Asmet Salud",
    "emssanar": "Emssanar E.S.S.",
    "capital salud": "Capital Salud EPS-S",
    "savia salud": "Savia Salud EPS",
    "dusakawi": "Dusakawi EPSI",
    "aic": "Asociación Indígena del Cauca EPSI",
    "anas wayuu": "Anas Wayuu EPSI",
    "mallamas": "Mallamas EPSI",
    "pijaos salud": "Pijaos Salud EPSI",
}


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
    "coosalud eps": "coosalud",
    "coosalud eps s": "coosalud",
    "mutualser": "mutual ser",
    "salud mia eps": "salud mia",
    "alianza salud": "aliansalud",
    "aliansalud eps": "aliansalud",
    "famisanar eps": "famisanar",
    "servicio occidental de salud": "sos",
    "eps sos": "sos",
    "s o s": "sos",
    "eps s o s": "sos",
    "comfenalco valle eps": "comfenalco valle",
    "cajacopi atlantico": "cajacopi",
    "capital salud eps": "capital salud",
    "savia salud eps": "savia salud",
    "aic epsi": "aic",
    "asociacion indigena del cauca": "aic",
    "pijao salud": "pijaos salud",
    "pijaos salud epsi": "pijaos salud",

    "fundacion santa fe de bogota":
        "fundacion santa fe",

    "fundacion santa fe":
        "fundacion santa fe",

    "hospital pablo tobon":
        "hospital pablo tobon uribe",

    "pablo tobon":
        "hospital pablo tobon uribe",
}


def reconocer_eps(entidad: str, umbral: float = 0.76) -> str | None:
    """Nombre canónico de una EPS conocida; nunca inventa una entidad."""
    q = normalizar(entidad)
    if not q:
        return None

    clave = ALIASES.get(q, q)
    if clave in EPS_VIGENTES:
        return EPS_VIGENTES[clave]

    candidatos = []
    for llave, nombre in EPS_VIGENTES.items():
        score = max(similitud(q, llave), similitud(q, nombre))
        candidatos.append((score, nombre))
    score, nombre = max(candidatos)
    return nombre if score >= umbral else None


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
        if clave in CANALES:
            return {
                "estado": "exacto",
                "canal": CANALES[clave],
            }
        if clave in EPS_VIGENTES:
            return {
                "estado": "eps_reconocida_sin_canal",
                "entidad": EPS_VIGENTES[clave],
                "canal": None,
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
        reconocida = reconocer_eps(entidad)
        return {
            "estado": "eps_reconocida_sin_canal" if reconocida else "no_encontrado",
            "entidad": reconocida,
            "canal": None,
        }

    return {
        "estado": "fuzzy",
        "score": mejor[0],
        "canal": mejor[2],
    }
