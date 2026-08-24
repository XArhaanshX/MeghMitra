"""FastAPI dependency wiring: request -> repository -> domain service.

Routes depend on the `get_*_service` functions only, never on repositories
or `app.state` directly. Tests override these with in-memory services via
`app.dependency_overrides` (see `tests/integration/test_rules_api.py`).
"""

from __future__ import annotations

from ankur_domain.repositories import DocumentRepository, ExtractionRunRepository, RuleRepository
from ankur_domain.services import DocumentService, ReviewService, RuleService
from fastapi import HTTPException, Request

from app.db import (
    PostgresDocumentRepository,
    PostgresExtractionRunRepository,
    PostgresRuleRepository,
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
    return ReviewService(rules=get_rule_repo(request))


def get_ingestion_service(request: Request) -> IngestionService:
    return IngestionService(
        documents=get_document_service(request),
        rules=get_rule_service(request),
        runs=get_run_repo(request),
    )
