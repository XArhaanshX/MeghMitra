"""FastAPI dependency wiring: request -> repository -> domain service.

Routes depend on the `get_*_service` functions only, never on repositories
or `app.state` directly. Tests override these with in-memory services via
`app.dependency_overrides` (see `tests/integration/test_rules_api.py`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ankur_domain.repositories import (
    AdvisoryRepository,
    DocumentRepository,
    ExtractionRunRepository,
    RuleRepository,
    TriggerEventRepository,
)
from ankur_domain.services import DocumentService, ReviewService, RuleService
from fastapi import HTTPException, Request

from app.advisory import AdvisoryEmissionService
from app.db import (
    PostgresAdvisoryRepository,
    PostgresDocumentRepository,
    PostgresExtractionRunRepository,
    PostgresRuleRepository,
    PostgresTriggerEventRepository,
)
from app.ingestion import IngestionService


def _pool(request: Request):
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="database unavailable")
    return pool


def get_document_repo(request: Request) -> DocumentRepository:
    return PostgresDocumentRepository(_pool(request))


def get_rule_repo(request: Request) -> RuleRepository:
    return PostgresRuleRepository(_pool(request))


def get_run_repo(request: Request) -> ExtractionRunRepository:
    return PostgresExtractionRunRepository(_pool(request))


def get_document_service(request: Request) -> DocumentService:
    return DocumentService(documents=get_document_repo(request))


def get_rule_service(request: Request) -> RuleService:
    return RuleService(rules=get_rule_repo(request))


def get_review_service(request: Request) -> ReviewService:
    return ReviewService(rules=get_rule_repo(request), documents=get_document_repo(request))


def get_ingestion_service(request: Request) -> IngestionService:
    return IngestionService(
        documents=get_document_service(request),
        rules=get_rule_service(request),
        runs=get_run_repo(request),
    )


def get_trigger_event_repo(request: Request) -> TriggerEventRepository:
    return PostgresTriggerEventRepository(_pool(request))


def get_advisory_repo(request: Request) -> AdvisoryRepository:
    return PostgresAdvisoryRepository(_pool(request))


def get_advisory_service(request: Request) -> AdvisoryEmissionService:
    return AdvisoryEmissionService(
        rules=get_rule_service(request),
        events=get_trigger_event_repo(request),
        advisories=get_advisory_repo(request),
        documents=get_document_repo(request),
    )



async def paginated(
    fetch: Callable[..., Awaitable[list[Any]]],
    *,
    limit: int | None,
    offset: int | None,
    count: Callable[[], Awaitable[int]] | None = None,
    default_limit: int = 50,
    count_limit: int = 1_000_000,
) -> list[Any] | dict[str, Any]:
    """Additive pagination envelope for GET list endpoints.

    `fetch(limit=..., offset=...)` is any service method already accepting
    those two keywords (`RuleService.list`, `DocumentService.list`,
    `ReviewService.review_queue`, `AdvisoryEmissionService.list_events`/
    `list_advisories`) with every other filter already bound (e.g. via a
    lambda). Returns the bare list when the caller passed neither `limit`
    nor `offset` explicitly -- so existing clients/tests that never asked
    for pagination keep getting exactly what they got before. Opting in to
    either one switches to `{"items", "total", "limit", "offset"}`.

    `total` prefers `count()` -- a real repository-level `COUNT(*)`
    (`RuleRepository.count`) -- when the caller supplies one. Without it,
    falls back to `len()` of a second, unbounded fetch of the same filters:
    correct but expensive (this is what re-fetched and re-deserialized the
    entire corpus on every `?limit=1` count-badge request from the
    frontend, and OOM'd the API in production once the corpus grew from
    the ~180-row demo seed to the ~9.4k-row full India ingestion -- see
    2026-08-28 in the vps GitOps changelog). Every current caller of this
    function passes `count` for exactly that reason; the fallback exists
    for future callers whose repository doesn't have a count method yet.
    """
    if limit is None and offset is None:
        return await fetch(limit=default_limit, offset=0)
    effective_limit = default_limit if limit is None else limit
    effective_offset = 0 if offset is None else offset
    page = await fetch(limit=effective_limit, offset=effective_offset)
    total = await count() if count is not None else len(await fetch(limit=count_limit, offset=0))
    return {
        "items": page,
        "total": total,
        "limit": effective_limit,
        "offset": effective_offset,
    }