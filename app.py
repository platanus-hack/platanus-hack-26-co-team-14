import logging

from fastapi import FastAPI

from canal.kapso import (
    router as kapso_router,
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s "
        "%(levelname)s "
        "%(name)s - "
        "%(message)s"
    ),
)


logger = logging.getLogger(
    __name__
)


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Platanus 2026 - Access",
    version="0.1.0",
)


# ============================================================
# ROUTERS
# ============================================================

app.include_router(
    kapso_router
)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
def root():
    return {
        "ok": True,
        "service": "Platanus2026",
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "status": "healthy",
    }


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup():
    logger.info(
        "Platanus2026 API iniciada"
    )