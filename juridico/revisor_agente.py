"""Compuerta de revisión jurídica asistida por IA para documentos ya renderizados."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from docx import Document

from juridico.render import iterar_parrafos

log = logging.getLogger("revisor_juridico")

BASE_DIR = Path(__file__).resolve().parent.parent
SKILL_DIR = BASE_DIR / "skills" / "revision-tutela"
MODELO = os.getenv("MODELO_REVISION_JURIDICA", "claude-sonnet-4-5-20250929")


class RevisionAgenteError(ValueError):
    """El documento no superó la compuerta de revisión final."""


def _instrucciones() -> str:
    rutas = [
        SKILL_DIR / "SKILL.md",
        SKILL_DIR / "references" / "checklist-redaccion.md",
        SKILL_DIR / "references" / "contrato-salida.md",
        SKILL_DIR / "references" / "uso-jurisprudencia.md",
    ]
    return "\n\n".join(ruta.read_text(encoding="utf-8") for ruta in rutas)


INSTRUCCIONES = _instrucciones()

HERRAMIENTA = {
    "name": "reportar_revision_final",
    "description": "Reporta la decisión y reemplazos exactos para el DOCX.",
    "input_schema": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["aprobar", "corregir", "bloquear"]},
            "resumen_judicial": {"type": "string"},
            "bloqueos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "regla": {"type": "string"},
                        "hallazgo": {"type": "string"},
                        "dato_faltante": {"type": ["string", "null"]},
                        "pregunta_usuario": {"type": ["string", "null"]},
                    },
                    "required": ["regla", "hallazgo", "dato_faltante", "pregunta_usuario"],
                },
            },
            "reemplazos": {
                "type": "array",
                "description": "Cambios literales y mínimos. 'anterior' debe existir completo.",
                "items": {
                    "type": "object",
                    "properties": {
                        "anterior": {"type": "string"},
                        "nuevo": {"type": "string"},
                        "motivo": {"type": "string"},
                    },
                    "required": ["anterior", "nuevo", "motivo"],
                },
            },
        },
        "required": ["decision", "resumen_judicial", "bloqueos", "reemplazos"],
    },
}


def _texto_docx(ruta: Path) -> str:
    doc = Document(ruta)
    return "\n".join(p.text for p in iterar_parrafos(doc) if p.text.strip())


def _valores_protegidos(contexto: dict, texto_original: str) -> set[str]:
    protegidos = set()
    for valor in contexto.values():
        if isinstance(valor, (str, int)):
            valor = str(valor).strip()
            if len(valor) >= 4 and valor in texto_original:
                protegidos.add(valor)
    return protegidos


def _aplicar_reemplazos(ruta: Path, reemplazos: list[dict], contexto: dict) -> None:
    doc = Document(ruta)
    original = "\n".join(p.text for p in iterar_parrafos(doc))
    protegidos = _valores_protegidos(contexto, original)

    for cambio in reemplazos:
        anterior = str(cambio.get("anterior") or "")
        nuevo = str(cambio.get("nuevo") or "")
        if not anterior or anterior == nuevo:
            continue
        coincidencias = sum(p.text.count(anterior) for p in iterar_parrafos(doc))
        if coincidencias != 1:
            raise RevisionAgenteError(
                "La corrección propuesta no identifica un fragmento único del documento.")
        for parrafo in iterar_parrafos(doc):
            if anterior in parrafo.text:
                texto = parrafo.text.replace(anterior, nuevo)
                # Un reemplazo mínimo de una locución nominal por un verbo
                # puede dejar «entregue del medicamento». Conservamos el
                # artículo del objeto directo sin permitir reescrituras libres.
                texto = re.sub(r"\b(entregue)\s+del\b", r"\1 el", texto)
                parrafo.text = texto
                break

    corregido = "\n".join(p.text for p in iterar_parrafos(doc))
    faltantes = sorted(valor for valor in protegidos if valor not in corregido)
    if faltantes:
        raise RevisionAgenteError(
            "La revisión intentó alterar datos confirmados de la persona.")
    doc.save(ruta)


def _habilitada() -> bool:
    valor = os.getenv("REVISION_JURIDICA_IA", "auto").strip().lower()
    if valor in {"0", "false", "no", "off"}:
        return False
    return valor in {"1", "true", "yes", "on"} or bool(os.getenv("ANTHROPIC_API_KEY"))


def revisar_documento(tipo: str, archivo: str | Path, contexto: dict,
                      client=None) -> dict:
    """Revisa el DOCX final, aplica correcciones seguras o bloquea su entrega."""
    ruta = Path(archivo)
    if not _habilitada() and client is None:
        return {"decision": "aprobar", "modo": "deterministico", "reemplazos": []}

    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    entrada = {
        "tipo_documento": "tutela" if tipo.startswith("tutela") else "derecho_peticion",
        "contexto_confirmado": contexto,
        "documento": _texto_docx(ruta),
    }
    try:
        respuesta = client.messages.create(
            model=MODELO,
            max_tokens=5000,
            system=INSTRUCCIONES + (
                "\n\nPara esta integración devuelve la revisión mediante la herramienta. "
                "Usa reemplazos literales mínimos; no cambies datos confirmados ni inventes "
                "hechos. Si falta un dato, bloquea en vez de insertar marcadores."),
            tools=[HERRAMIENTA],
            tool_choice={"type": "tool", "name": "reportar_revision_final"},
            messages=[{"role": "user", "content": json.dumps(
                entrada, ensure_ascii=False, default=str)}],
        )
        resultado = next(b.input for b in respuesta.content if b.type == "tool_use")
    except Exception as exc:
        log.exception("falló el agente de revisión jurídica")
        raise RevisionAgenteError(
            "No fue posible completar la revisión jurídica final.") from exc

    decision = resultado.get("decision")
    if decision == "bloquear":
        preguntas = [b.get("pregunta_usuario") for b in resultado.get("bloqueos", [])]
        detalle = next((p for p in preguntas if p), resultado.get("resumen_judicial"))
        raise RevisionAgenteError(str(detalle or "El documento requiere información adicional."))
    if decision == "corregir":
        reemplazos = resultado.get("reemplazos") or []
        if not reemplazos:
            raise RevisionAgenteError(
                "La revisión pidió corregir el documento, pero no entregó una corrección segura.")
        _aplicar_reemplazos(ruta, reemplazos, contexto)
    elif decision != "aprobar":
        raise RevisionAgenteError("La revisión jurídica devolvió una decisión inválida.")

    resultado["modo"] = "agente"
    return resultado
