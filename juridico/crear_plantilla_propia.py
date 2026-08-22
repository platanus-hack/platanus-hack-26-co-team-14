"""Deriva la tutela a nombre propio de la minuta adulta existente.

La estructura, fundamentos, pretensiones y formato salen de la plantilla del
repositorio. Solo se sustituyen o retiran las cláusulas exclusivas de agencia
oficiosa, para no afirmar que existe un tercero cuando accionante y paciente
son la misma persona.
"""

from pathlib import Path

from docx import Document


BASE = Path(__file__).parent / "plantillas"
ORIGEN = BASE / "tutela_agente_preparada.docx"
DESTINO = BASE / "tutela_propia_preparada.docx"


REEMPLAZOS = {
    1: "MODELO DE MINUTA DE TUTELA EN NOMBRE PROPIO",
    12: "ACCIONANTE: {{nombre_agente}}",
    18: (
        "{{nombre_agente}}, mayor de edad, identificado con cédula de ciudadanía "
        "No. {{cedula_agente}}, expedida en {{lugar_expedicion_agente}}, actuando "
        "en nombre propio, presento ACCIÓN DE TUTELA contra {{eps}} EPS para que "
        "se protejan mis derechos fundamentales a la vida, la salud, la dignidad "
        "humana y la seguridad social, con fundamento en lo siguiente."
    ),
    22: "PRIMERO: Me encuentro afiliado al Sistema de Seguridad Social en Salud en {{eps}} EPS.",
    24: "SEGUNDO: Tengo diagnóstico de {{diagnostico}}.",
    28: "CUARTO: La EPS {{eps}} vulneró mis derechos de la siguiente manera: {{hecho_vulneracion}}",
    30: (
        "QUINTO: Solicito atención integral, oportuna y sin barreras administrativas "
        "para mi diagnóstico y de acuerdo con las órdenes de mis médicos tratantes."
    ),
    33: "SEXTO: Presento esta acción porque necesito una protección inmediata y eficaz de mis derechos fundamentales.",
    36: "",
    38: "SÉPTIMO: La conducta de {{eps}} amenaza mis derechos fundamentales a la vida, la salud y la dignidad humana.",
    40: "Por lo anterior acudo a la tutela, pues no cuento con otro medio judicial con igual efectividad y rapidez.",
    155: "Que se me brinde atención médica integral para mi diagnóstico, de acuerdo con las órdenes de los médicos tratantes.",
    159: (
        "Con fundamento en el artículo 7 del Decreto 2591 de 1991, solicito como "
        "medida provisional que se ordene autorizar de manera inmediata {{servicio_urgente}}."
    ),
    161: "",
    164: (
        "Es competente el juez con jurisdicción en {{ciudad_vulneracion}}, lugar "
        "donde ocurre la vulneración, conforme al artículo 37 del Decreto 2591 de 1991."
    ),
    168: "Solicito tener como pruebas los documentos que adjunto para demostrar la vulneración de mis derechos.",
    172: "Fotocopia de mi cédula de ciudadanía.",
    173: "",
}


def crear() -> Path:
    doc = Document(ORIGEN)
    for indice, texto in REEMPLAZOS.items():
        doc.paragraphs[indice].text = texto
    doc.save(DESTINO)
    return DESTINO


if __name__ == "__main__":
    print(crear())
