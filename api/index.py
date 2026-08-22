"""Entrypoint para Vercel. Vercel busca la app ASGI aquí.

Importa `app.py` de la raíz —no `puente/app.py`— porque es ahí donde el
puente queda enchufado al cerebro. Importar el puente a secas desplegaría
un canal que contesta en eco.
"""

from app import app

__all__ = ["app"]
