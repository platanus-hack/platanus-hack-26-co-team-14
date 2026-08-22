import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path


RUTA_DATOS = Path(__file__).parent / "lookup_juzgados.json"

UMBRAL_FUZZY = 0.78
UMBRAL_AMBIGUEDAD = 0.05


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalizar(texto: str | None) -> str:
    if not texto:
        return ""

    texto = str(texto).strip().lower()

    texto = "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )

    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    texto = " ".join(texto.split())

    # El directorio usa «Bogotá D.C.» y la ciudadanía suele decir «Bogotá».
    # Para resolver territorio son el mismo distrito.
    if texto.endswith(" d c"):
        texto = texto[:-4].strip()

    return texto


# ============================================================
# CARGA
# ============================================================

def cargar_juzgados():
    with open(
        RUTA_DATOS,
        "r",
        encoding="utf-8",
    ) as f:
        datos = json.load(f)

    if not isinstance(datos, list):
        raise ValueError(
            "lookup_juzgados.json debe contener una lista."
        )

    return datos


JUZGADOS = cargar_juzgados()


# ============================================================
# CLASIFICACIÓN
# ============================================================

def es_destino_no_preferido(registro: dict) -> bool:
    """
    Penaliza oficinas que existen en el directorio pero
    no queremos seleccionar automáticamente como primera
    opción para la presentación de una tutela.
    """

    nombre = normalizar(
        registro.get("nombre")
    )

    terminos = [
        "restitucion tierras",
        "tribunal administrativo",
    ]

    return any(
        termino in nombre
        for termino in terminos
    )


def prioridad_registro(registro: dict) -> int:
    """
    Menor = mejor.

    Preferimos:
    1. reparto
    2. juzgado ordinario municipal
    3. otros juzgados
    4. oficinas especializadas
    """

    tipo = normalizar(
        registro.get("tipo")
    )

    nombre = normalizar(
        registro.get("nombre")
    )

    if es_destino_no_preferido(registro):
        return 100

    if tipo == "reparto":
        return 0

    if "promiscuo municipal" in nombre:
        return 10

    if "civil municipal" in nombre:
        return 10

    if tipo == "juzgado":
        return 20

    return 50


# ============================================================
# BÚSQUEDA EXACTA
# ============================================================

def buscar_exactos(
    ciudad: str,
    departamento: str | None = None,
):
    ciudad_norm = normalizar(ciudad)
    depto_norm = normalizar(departamento)

    resultados = []

    for registro in JUZGADOS:
        if (
            normalizar(registro.get("ciudad_norm"))
            != ciudad_norm
        ):
            continue

        if (
            depto_norm
            and normalizar(registro.get("depto_norm"))
            != depto_norm
        ):
            continue

        resultados.append(registro)

    return resultados


# ============================================================
# FUZZY
# ============================================================

def similitud(a: str, b: str) -> float:
    return SequenceMatcher(
        None,
        normalizar(a),
        normalizar(b),
    ).ratio()


def buscar_fuzzy(
    ciudad: str,
    departamento: str | None = None,
):
    ciudad_norm = normalizar(ciudad)
    depto_norm = normalizar(departamento)

    candidatos = []

    for registro in JUZGADOS:

        # Si conocemos departamento, no buscamos fuera de él.
        if (
            depto_norm
            and normalizar(registro.get("depto_norm"))
            != depto_norm
        ):
            continue

        score_ciudad = similitud(
            ciudad_norm,
            registro.get("ciudad_norm", ""),
        )

        if score_ciudad < UMBRAL_FUZZY:
            continue

        candidatos.append({
            "registro": registro,
            "score": score_ciudad,
        })

    candidatos.sort(
        key=lambda x: (
            -x["score"],
            prioridad_registro(x["registro"]),
        )
    )

    return candidatos


# ============================================================
# SELECCIÓN ENTRE VARIOS REGISTROS DEL MISMO MUNICIPIO
# ============================================================

def seleccionar_destino(registros: list[dict]):
    if not registros:
        return None

    return sorted(
        registros,
        key=prioridad_registro,
    )[0]


# ============================================================
# RESOLUCIÓN PRINCIPAL
# ============================================================

def resolver_juzgado(
    ciudad: str,
    departamento: str | None = None,
):
    """
    Estados posibles:

    exacto
    fuzzy
    ambiguo
    no_encontrado

    Nunca inventa un juzgado.
    """

    if not ciudad:
        return {
            "estado": "falta_ciudad",
            "registro": None,
            "alternativas": [],
        }

    # --------------------------------------------------------
    # 1. Exacto
    # --------------------------------------------------------

    exactos = buscar_exactos(
        ciudad,
        departamento,
    )

    if exactos:
        elegido = seleccionar_destino(
            exactos
        )

        return {
            "estado": "exacto",
            "score": 1.0,
            "registro": elegido,
            "alternativas": [
                r
                for r in exactos
                if r is not elegido
            ],
        }

    # --------------------------------------------------------
    # 2. Fuzzy
    # --------------------------------------------------------

    fuzzy = buscar_fuzzy(
        ciudad,
        departamento,
    )

    if not fuzzy:
        return {
            "estado": "no_encontrado",
            "registro": None,
            "alternativas": [],
        }

    mejor = fuzzy[0]

    # --------------------------------------------------------
    # 3. Detectar ambigüedad entre municipios
    # --------------------------------------------------------

    municipios = {}

    for candidato in fuzzy:
        registro = candidato["registro"]

        clave = (
            registro.get("depto_norm"),
            registro.get("ciudad_norm"),
        )

        if clave not in municipios:
            municipios[clave] = candidato

    mejores_municipios = sorted(
        municipios.values(),
        key=lambda x: -x["score"],
    )

    if len(mejores_municipios) > 1:
        primero = mejores_municipios[0]
        segundo = mejores_municipios[1]

        diferencia = (
            primero["score"]
            - segundo["score"]
        )

        if diferencia < UMBRAL_AMBIGUEDAD:
            return {
                "estado": "ambiguo",
                "registro": None,
                "score": primero["score"],
                "alternativas": [
                    x["registro"]
                    for x in mejores_municipios[:5]
                ],
            }

    # --------------------------------------------------------
    # 4. Municipio fuzzy resuelto
    # --------------------------------------------------------

    municipio = mejor["registro"].get(
        "ciudad_norm"
    )

    depto = mejor["registro"].get(
        "depto_norm"
    )

    registros_municipio = [
        x["registro"]
        for x in fuzzy
        if (
            x["registro"].get("ciudad_norm")
            == municipio
            and x["registro"].get("depto_norm")
            == depto
        )
    ]

    elegido = seleccionar_destino(
        registros_municipio
    )

    return {
        "estado": "fuzzy",
        "score": mejor["score"],
        "registro": elegido,
        "alternativas": [
            r
            for r in registros_municipio
            if r is not elegido
        ],
    }


# ============================================================
# CONTEXTO PARA DOCUMENTO
# ============================================================

def limpiar_nombre_destino(
    registro: dict,
) -> str:
    """
    Convierte el nombre del directorio en texto para
    encabezado.

    Ej:
    Juzgado 01 Promiscuo Municipal - Amazonas - Puerto Nariño

    ->
    JUZGADO 01 PROMISCUO MUNICIPAL DE PUERTO NARIÑO
    """

    nombre = (
        registro.get("nombre")
        or "JUEZ CONSTITUCIONAL"
    )

    ciudad = (
        registro.get("ciudad")
        or ""
    )

    # Quitamos sufijos territoriales generados por el ETL.
    if " - " in nombre:
        nombre = nombre.split(" - ")[0]

    if ciudad:
        if normalizar(ciudad) not in normalizar(nombre):
            nombre = (
                f"{nombre} DE {ciudad}"
            )

    return nombre.upper()


def contexto_juzgado(
    ciudad: str,
    departamento: str | None = None,
):
    resultado = resolver_juzgado(
        ciudad,
        departamento,
    )

    registro = resultado.get(
        "registro"
    )

    if not registro:
        return {
            "estado_juzgado":
                resultado["estado"],

            "juez_destino":
                "JUEZ CONSTITUCIONAL (REPARTO)",

            "ciudad_juzgado":
                ciudad.upper()
                if ciudad
                else None,

            "departamento_juzgado":
                departamento.upper()
                if departamento
                else None,

            "email_juzgado":
                None,

            "dane_juzgado":
                None,

            "tipo_juzgado":
                None,

            "requiere_revision_juzgado":
                True,

            "alternativas_juzgado":
                resultado.get(
                    "alternativas",
                    [],
                ),
        }

    return {
        "estado_juzgado":
            resultado["estado"],

        "juez_destino":
            limpiar_nombre_destino(
                registro
            ),

        "ciudad_juzgado":
            registro.get("ciudad"),

        "departamento_juzgado":
            registro.get("depto"),

        "email_juzgado":
            registro.get("email"),

        "dane_juzgado":
            registro.get("dane"),

        "tipo_juzgado":
            registro.get("tipo"),

        "requiere_revision_juzgado":
            resultado["estado"]
            not in {"exacto", "fuzzy"},

        "alternativas_juzgado":
            resultado.get(
                "alternativas",
                [],
            ),
    }
