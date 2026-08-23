"""Control final del contenido jurídico antes de renderizar la minuta."""

from __future__ import annotations

import re
from copy import deepcopy


class RevisionJuridicaError(ValueError):
    pass


def _normalizar(texto) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(texto or "").lower()).split())


def revisar_contexto(tipo: str, contexto: dict) -> dict:
    """Corrige lo seguro y bloquea contradicciones antes de crear el DOCX.

    La revisión probabilística podrá enriquecer este contexto en el futuro,
    pero nunca podrá saltarse estas reglas.
    """
    revisado = deepcopy(contexto)
    principal = _normalizar(revisado.get("servicio_solicitado"))
    provisional = _normalizar(revisado.get("servicio_urgente"))

    if revisado.get("_incluir_medida_provisional"):
        if not provisional or provisional == principal:
            raise RevisionJuridicaError(
                "La medida provisional no puede repetir la pretensión principal.")
        if not any(x in provisional for x in ("mientras", "provisional", "temporal")):
            raise RevisionJuridicaError(
                "La medida provisional debe indicar su carácter temporal.")
        if not any(x in provisional for x in ("evitar", "demora", "agrave", "daño")):
            raise RevisionJuridicaError(
                "La medida provisional debe explicar el peligro en la demora.")

    if tipo == "tutela_propia":
        texto = " ".join(str(v) for v in revisado.values())
        if "agente oficioso" in texto.lower():
            raise RevisionJuridicaError(
                "Una tutela propia no puede afirmar agencia oficiosa.")

    return revisado
