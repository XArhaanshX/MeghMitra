"""RuleService filtering: advisory-eligible is approved+cited, not high-confidence."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from ankur_domain.memory import InMemoryRuleRepository
from ankur_domain.services import RuleService
from ankur_schemas.citation import Citation
from ankur_schemas.condition import ConditionCode
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRule, DACPRuleFields


def _rule(
    *,
    district: str = "Sirsa",
    status: ReviewStatus = ReviewStatus.APPROVED,
    page: int = 7,
    document: str = "HAR16-Sirsa-30-06-2011.pdf",
    code: ConditionCode | None = ConditionCode.DRY_SPELL_AFTER_SOWING,
) -> DACPRule:
    return DACPRule(
        fields=DACPRuleFields(
            district=district,
            condition="Normal onset followed by 15-20 day dry spell after sowing",
            condition_code=code,
        ),
        citation=Citation(document=document, page=page),
        confidence=0.94,
        extractor_version="test",
        extracted_at=datetime.now(UTC),
        review_status=status,
    )


@pytest.fixture
def service() -> RuleService:
    repo = InMemoryRuleRepository()
    asyncio.run(repo.add(_rule()))
    asyncio.run(repo.add(_rule(status=ReviewStatus.PENDING, page=8)))
    asyncio.run(repo.add(_rule(district="Hisar", page=9)))
    asyncio.run(_add_uncited(repo))
    return RuleService(rules=repo)


async def _add_uncited(repo: InMemoryRuleRepository) -> None:
    await repo.add(_rule(status=ReviewStatus.APPROVED, document="", page=1, code=None))


def test_list_advisory_eligible_excludes_pending_and_uncited(service: RuleService):
    eligible = asyncio.run(service.list_advisory_eligible())
    assert len(eligible) == 2
    assert all(r.review_status == ReviewStatus.APPROVED for r in eligible)
    assert all(r.citation.document for r in eligible)


def test_list_advisory_eligible_filters_district(service: RuleService):
    sirsa = asyncio.run(service.list_advisory_eligible(district="Sirsa"))
    assert len(sirsa) == 1
    assert sirsa[0].fields.district == "Sirsa"


def test_list_by_district_still_includes_pending(service: RuleService):
    sirsa = asyncio.run(service.list(district="Sirsa"))
    statuses = {r.review_status for r in sirsa}
    assert ReviewStatus.PENDING in statuses
    assert ReviewStatus.APPROVED in statuses
