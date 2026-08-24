"""Advisory emission through FastAPI, in-memory repos, no live Postgres.

The product claim under test: Ankur retrieves an approved cited rule or stays
silent. A pending/rejected/uncited row must never become an advisory, even when
the weather would otherwise match.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from ankur_domain.memory import (
    InMemoryAdvisoryRepository,
    InMemoryDocumentRepository,
    InMemoryRuleRepository,
    InMemoryTriggerEventRepository,
)
from ankur_domain.services import DocumentService, ReviewService, RuleService
from ankur_schemas.condition import ConditionCode
from ankur_schemas.enums import ReviewStatus
from app.advisory import AdvisoryEmissionService
from app.deps import (
    get_advisory_service,
    get_document_service,
    get_review_service,
    get_rule_service,
)
from app.main import app
from fastapi.testclient import TestClient
from pytest import fixture


def _moisture(**overrides: object) -> dict:
    body = {
        "block_id": "sirsa-block-1",
        "as_of": "2020-07-15",
        "soil_moisture_fraction": 0.8,
        "consecutive_dry_days": 0,
        "days_since_sowing": None,
        "onset_delay_days": None,
        "rain_3d_mm": 10.0,
        "rain_3d_normal_mm": 10.0,
    }
    body.update(overrides)
    return body


def _forecast(*, probability: float = 0.8) -> dict:
    return {
        "block_id": "sirsa-block-1",
        "issued_on": "2020-07-15",
        "lead_days": 14,
        "probability": probability,
        "climatological_rate": 0.2,
        "model_version": "trigger-engine/0.1.0",
    }


def _evaluate_body(*, moisture: dict | None = None, **extra: object) -> dict:
    body: dict = {
        "district": "Sirsa",
        "moisture": moisture or _moisture(),
        "forecast": _forecast(),
        "crop_already_sown": False,
    }
    body.update(extra)
    return body


@fixture
def rule_repo(sirsa_rules) -> InMemoryRuleRepository:
    repo = InMemoryRuleRepository()
    for rule in sirsa_rules:
        asyncio.run(repo.add(rule))
    return repo


@fixture
def event_repo() -> InMemoryTriggerEventRepository:
    return InMemoryTriggerEventRepository()


@fixture
def advisory_repo() -> InMemoryAdvisoryRepository:
    return InMemoryAdvisoryRepository()


@fixture
def client(
    rule_repo: InMemoryRuleRepository,
    event_repo: InMemoryTriggerEventRepository,
    advisory_repo: InMemoryAdvisoryRepository,
):
    doc_repo = InMemoryDocumentRepository()
    rule_service = RuleService(rules=rule_repo)
    app.dependency_overrides[get_rule_service] = lambda: rule_service
    app.dependency_overrides[get_review_service] = lambda: ReviewService(
        rules=rule_repo, documents=doc_repo
    )
    app.dependency_overrides[get_document_service] = lambda: DocumentService(documents=doc_repo)
    app.dependency_overrides[get_advisory_service] = lambda: AdvisoryEmissionService(
        rules=rule_service,
        events=event_repo,
        advisories=advisory_repo,
        documents=doc_repo,
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_ordinary_weather_abstains_and_is_audited(
    client: TestClient,
    event_repo: InMemoryTriggerEventRepository,
    advisory_repo: InMemoryAdvisoryRepository,
):
    resp = client.post("/advisories", json=_evaluate_body())
    assert resp.status_code == 201
    body = resp.json()
    assert body["action"] == "abstain"
    assert body["detected_condition"] is None
    assert body["rule"] is None
    assert body["citation"] is None
    assert "no condition detected" in body["abstain_reasons"]
    assert asyncio.run(event_repo.list())
    assert asyncio.run(advisory_repo.list()) == []


def test_dry_spell_after_sowing_retrieves_the_approved_pearl_millet_rule(client: TestClient):
    resp = client.post(
        "/advisories",
        json=_evaluate_body(
            moisture=_moisture(
                soil_moisture_fraction=0.2,
                consecutive_dry_days=10,
                days_since_sowing=10,
            ),
            crop_already_sown=True,
        ),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["action"] == "re_sow"
    assert body["detected_condition"] == ConditionCode.DRY_SPELL_AFTER_SOWING
    assert body["rule"]["fields"]["crop"] == "Pearl millet"
    assert body["rule"]["fields"]["variety"] == "HHB-67 Improved"
    assert body["citation"]["document"] == "HAR16-Sirsa-30-06-2011.pdf"
    assert body["abstain_reasons"] == []
    UUID(body["trigger_event_id"])


def test_same_weather_before_sowing_is_wait_not_re_sow(client: TestClient):
    resp = client.post(
        "/advisories",
        json=_evaluate_body(
            moisture=_moisture(
                soil_moisture_fraction=0.2,
                consecutive_dry_days=10,
                days_since_sowing=10,
            ),
            crop_already_sown=False,
        ),
    )
    assert resp.status_code == 201
    assert resp.json()["action"] == "wait"


def test_pending_delayed_onset_rule_cannot_fire(client: TestClient):
    """The cotton delayed-onset row is coded but still pending — silence."""
    resp = client.post(
        "/advisories",
        json=_evaluate_body(moisture=_moisture(onset_delay_days=25)),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["action"] == "abstain"
    assert body["detected_condition"] == ConditionCode.DELAYED_ONSET
    assert body["rule"] is None
    assert "no matching approved rule" in body["abstain_reasons"]


def test_rejected_unseasonal_rain_rule_cannot_fire(client: TestClient):
    resp = client.post(
        "/advisories",
        json=_evaluate_body(moisture=_moisture(rain_3d_mm=50.0, rain_3d_normal_mm=10.0)),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["action"] == "abstain"
    assert body["detected_condition"] == ConditionCode.UNSEASONAL_RAIN
    assert body["rule"] is None


def test_other_district_does_not_see_sirsa_rules(client: TestClient):
    resp = client.post(
        "/advisories",
        json=_evaluate_body(
            district="Hisar",
            moisture=_moisture(
                soil_moisture_fraction=0.2,
                consecutive_dry_days=10,
                days_since_sowing=10,
            ),
            crop_already_sown=True,
        ),
    )
    assert resp.status_code == 201
    assert resp.json()["action"] == "abstain"
    assert resp.json()["rule"] is None


def test_list_advisory_eligible_rules_via_query_param(client: TestClient):
    resp = client.get("/rules", params={"advisory_eligible": True})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["review_status"] == ReviewStatus.APPROVED
    assert rows[0]["fields"]["crop"] == "Pearl millet"


def test_firing_advisory_is_listed(client: TestClient):
    fire = client.post(
        "/advisories",
        json=_evaluate_body(
            moisture=_moisture(
                soil_moisture_fraction=0.2,
                consecutive_dry_days=10,
                days_since_sowing=10,
            ),
            crop_already_sown=True,
        ),
    )
    assert fire.status_code == 201

    listed = client.get("/advisories")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["action"] == "re_sow"

    events = client.get("/trigger-events")
    assert events.status_code == 200
    assert len(events.json()) == 1
    assert events.json()[0]["condition"] == "dry_spell_after_sowing"


def test_evaluate_requires_moisture_and_forecast(client: TestClient):
    resp = client.post("/advisories", json={"district": "Sirsa"})
    assert resp.status_code == 422
