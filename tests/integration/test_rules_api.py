"""FastAPI integration tests, wired to in-memory repositories via
`app.dependency_overrides` -- no real Postgres required.

Covers spec invariant 8 (approved rule can be queried through the API) and
exercises the review workflow end to end through HTTP.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from ankur_domain.memory import InMemoryDocumentRepository, InMemoryRuleRepository
from ankur_domain.services import DocumentService, ReviewService, RuleService
from ankur_schemas.citation import Citation
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRule, DACPRuleFields
from app.deps import get_document_service, get_review_service, get_rule_service
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def rule_repo(sirsa_rules) -> InMemoryRuleRepository:
    repo = InMemoryRuleRepository()
    for rule in sirsa_rules:
        asyncio.run(repo.add(rule))
    return repo


@pytest.fixture
def client(rule_repo: InMemoryRuleRepository):
    doc_repo = InMemoryDocumentRepository()
    app.dependency_overrides[get_rule_service] = lambda: RuleService(rules=rule_repo)
    app.dependency_overrides[get_review_service] = lambda: ReviewService(rules=rule_repo)
    app.dependency_overrides[get_document_service] = lambda: DocumentService(documents=doc_repo)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_rules_returns_fixture_rules(client: TestClient, sirsa_rules):
    resp = client.get("/rules")
    assert resp.status_code == 200
    assert len(resp.json()) == len(sirsa_rules)


def test_get_rule_and_its_citation(client: TestClient, sirsa_rules):
    rule = sirsa_rules[0]
    resp = client.get(f"/rules/{rule.id}")
    assert resp.status_code == 200
    assert resp.json()["fields"]["crop"] == "Pearl millet"

    citation_resp = client.get(f"/rules/{rule.id}/citation")
    assert citation_resp.status_code == 200
    assert citation_resp.json()["page"] == 37


def test_get_unknown_rule_is_404(client: TestClient):
    resp = client.get("/rules/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_review_queue_only_lists_needs_review(client: TestClient, sirsa_rules):
    resp = client.get("/review-queue")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    expected = {str(r.id) for r in sirsa_rules if r.review_status == ReviewStatus.NEEDS_REVIEW}
    assert ids == expected


def test_approved_rule_is_queryable_through_the_api(client: TestClient, sirsa_rules):
    """Spec invariant 8: an approved rule can be queried through the API."""
    approved = next(r for r in sirsa_rules if r.review_status == ReviewStatus.APPROVED)
    resp = client.get(f"/rules/{approved.id}")
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "approved"


def test_approve_pending_rule_with_valid_citation(client: TestClient, sirsa_rules):
    pending = next(r for r in sirsa_rules if r.review_status == ReviewStatus.PENDING)
    resp = client.post(f"/rules/{pending.id}/approve", json={"reviewed_by": "reviewer@icar-crida"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_status"] == "approved"
    assert body["reviewed_by"] == "reviewer@icar-crida"


def test_reject_rule(client: TestClient, sirsa_rules):
    pending = next(r for r in sirsa_rules if r.review_status == ReviewStatus.PENDING)
    resp = client.post(
        f"/rules/{pending.id}/reject",
        json={"reviewed_by": "reviewer@icar-crida", "reason": "ambiguous row"},
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "rejected"


def test_approve_rule_without_citation_is_rejected_by_the_api(
    client: TestClient, rule_repo: InMemoryRuleRepository
):
    """Core invariant enforced at the HTTP boundary too: no citation -> no approved rule."""
    uncited = DACPRule(
        fields=DACPRuleFields(district="Sirsa", condition="some condition"),
        citation=Citation(document="", page=1),
        confidence=0.95,
        extractor_version="document-intelligence/0.1.0",
        extracted_at=datetime.now(UTC),
        review_status=ReviewStatus.PENDING,
    )
    asyncio.run(rule_repo.add(uncited))

    resp = client.post(f"/rules/{uncited.id}/approve", json={"reviewed_by": "reviewer@icar-crida"})

    assert resp.status_code == 422
    assert asyncio.run(rule_repo.get(uncited.id)).review_status == ReviewStatus.PENDING
