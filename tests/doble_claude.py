"""
Un Claude de mentira, para probar el flujo sin gastar llamadas ni llaves.

`extraccion.extraer()` acepta un `client`. Este objeto imita lo justo de
`anthropic.Anthropic`: `client.messages.create(...)` devuelve algo con
`.content`, y ahí dentro un bloque `tool_use` con el diccionario de slots.

Cómo sabe qué contestar: lee la pista que `extraer()` mete en el prompt
("La última pregunta que se le hizo fue sobre: X") y responde al guion. En el
primer turno, cuando no hay pista, suelta el bloque inicial.

La evidencia siempre es el texto entero de la usuaria, para que pase el
control antialucinación de `verificar_evidencia`.
"""

from __future__ import annotations

import re


class _Bloque:
    type = "tool_use"

    def __init__(self, entrada: dict):
        self.input = entrada


class _Respuesta:
    def __init__(self, entrada: dict):
        self.content = [_Bloque(entrada)]


class _Mensajes:
    def __init__(self, doble):
        self._doble = doble

    def create(self, **kwargs):
        texto = kwargs["messages"][0]["content"]
        return _Respuesta(self._doble.responder(texto))


class ClaudeDoble:
    """`inicial` es lo que se extrae del primer audio.
    `guion` es {slot: valor} para cada pregunta posterior."""

    def __init__(self, inicial: dict, guion: dict | None = None,
                 confianza: float = 0.95):
        self.inicial = inicial
        self.guion = guion or {}
        self.confianza = confianza
        self.messages = _Mensajes(self)
        self.preguntado: list[str] = []

    def responder(self, prompt: str) -> dict:
        dicho = prompt.split("Lo que dijo la persona:", 1)[-1]
        dicho = dicho.split("La última pregunta", 1)[0].strip()

        esperando = None
        if m := re.search(r"La última pregunta que se le hizo fue sobre: (\w+)",
                          prompt):
            esperando = m.group(1)
            self.preguntado.append(esperando)

        if esperando is None:
            valores = self.inicial
        elif esperando in self.guion:
            valores = {esperando: self.guion[esperando]}
        else:
            valores = {}

        return {
            campo: {
                "valor": valor,
                # Un `False` necesita mucha más certeza que un `True`:
                # los umbrales de extraccion.py son asimétricos a propósito.
                "confianza": 0.99 if valor is False else self.confianza,
                "evidencia": dicho,
            }
            for campo, valor in valores.items()
        }
