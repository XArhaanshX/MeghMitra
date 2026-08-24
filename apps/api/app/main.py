"""Ankur API entry point.

`uvicorn app.main:app --reload` (see `make dev`). Routes are thin; all
business logic lives in `ankur_domain` services, wired via `app.deps`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from app.config import get_settings
from app.db import create_pool
from app.routes import documents, health, review, rules

logger = logging.getLogger("ankur.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    try:
        app.state.pool = await create_pool(settings.database_url)
        logger.info("connected to database")
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        # Expected in local dev when Postgres isn't up yet (make docker-up
        # not run, or still starting) -- one clear line, no traceback noise.
        app.state.pool = None
        logger.warning("database unavailable at startup (%s); DB-backed routes will 503", exc)
    except Exception:  # noqa: BLE001 - startup must not crash the process without DB
        app.state.pool = None
        logger.warning("database unavailable at startup; DB-backed routes will 503", exc_info=True)

    yield

    if app.state.pool is not None:
        await app.state.pool.close()


app = FastAPI(
    title="Ankur API",
    description=(
        "Retrieves pre-approved DACP contingency actions and their citations. "
        "Never generates agricultural advice."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(rules.router)
app.include_router(review.router)
