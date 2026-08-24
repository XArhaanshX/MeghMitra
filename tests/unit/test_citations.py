"""Citation/provenance invariants.

Covers spec invariant 4 (rule -> citation) and the core product invariant:
**no citation -> no approved rule.**
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ankur_domain.memory import InMemoryDocumentRepository, InMemoryRuleRepository
from ankur_domain.policies import can_approve, has_valid_citation
from ankur_domain.services import ReviewService, RuleNotApprovableError, RuleService
from ankur_schemas.citation import Citation
from ankur_schemas.document import DocumentMetadata
from ankur_schemas.enums import DocumentStatus, ReviewStatus
from ankur_schemas.rule import DACPRule, DACPRuleFields


def _rule(citation: Citation, **overrides) -> DACPRule:
    fields = DACPRuleFields(district="Sirsa", condition="dry spell")
    defaults = dict(
        fields=fields,
        citation=citation,
        confidence=0.9,
        extractor_version="document-intelligence/0.1.0",
        extracted_at=datetime.now(UTC),
        review_status=ReviewStatus.PENDING,
    )
    defaults.update(overrides)
    return DACPRule(**defaults)


def test_rule_carries_document_and_page_citation(sirsa_rules):
    rule = sirsa_rules[0]
    assert rule.citation.document == "HAR16-Sirsa-30-06-2011.pdf"
    assert rule.citation.page == 37


def test_has_valid_citation_requires_document_and_positive_page():
    assert has_valid_citation(Citation(document="plan.pdf", page=1)) is True
    assert has_valid_citation(Citation(document="", page=1)) is False
    assert has_valid_citation(None) is False


def test_can_approve_rejects_missing_citation():
    rule = _rule(Citation(document="", page=1))
    ok, reason = can_approve(rule)
    assert ok is False
    assert "citation" in reason


def test_can_approve_accepts_valid_citation():
    rule = _rule(Citation(document="plan.pdf", page=5))
    ok, reason = can_approve(rule)
    assert ok is True
    assert reason is None


def test_has_valid_citation_rejects_page_beyond_document():
    citation = Citation(document="plan.pdf", page=37)
    assert has_valid_citation(citation) is True
    assert has_valid_citation(citation, page_count=31) is False
    assert has_valid_citation(citation, page_count=37) is True


def test_can_approve_rejects_page_past_end():
    rule = _rule(Citation(document="plan.pdf", page=37))
    ok, reason = can_approve(rule, page_count=31)
    assert ok is False
    assert "page" in reason
    assert can_approve(rule)[0] is True  # unbound call sites unchanged


@pytest.mark.asyncio
async def test_review_service_refuses_to_approve_uncited_rule():
    """End-to-end: the approve workflow itself blocks on a missing citation,
    independent of whatever review_status the rule already had.
    """
    repo = InMemoryRuleRepository()
    rule = _rule(Citation(document="", page=1), review_status=ReviewStatus.PENDING)
    await repo.add(rule)
    service = ReviewService(rules=repo)

    with pytest.raises(RuleNotApprovableError):
        await service.approve(rule.id, reviewed_by="tester")

    stored = await repo.get(rule.id)
    assert stored.review_status == ReviewStatus.PENDING  # unchanged


@pytest.mark.asyncio
async def test_review_service_refuses_page_past_document_end():
    rules = InMemoryRuleRepository()
    documents = InMemoryDocumentRepository()
    document = DocumentMetadata(
        filename="HAR16-Sirsa-30-06-2011.pdf",
        district="Sirsa",
        state="Haryana",
        page_count=31,
        registered_at=datetime.now(UTC),
        status=DocumentStatus.REGISTERED,
    )
    await documents.add(document)
    rule = _rule(
        Citation(document=document.filename, page=37),
        document_id=document.id,
        review_status=ReviewStatus.PENDING,
    )
    await rules.add(rule)
    service = ReviewService(rules=rules, documents=documents)

    with pytest.raises(RuleNotApprovableError, match="page"):
        await service.approve(rule.id, reviewed_by="tester")

    stored = await rules.get(rule.id)
    assert stored.review_status == ReviewStatus.PENDING


@pytest.mark.asyncio
async def test_record_extracted_refuses_approved_status():
    """Extraction persistence is not an approval path."""
    repo = InMemoryRuleRepository()
    service = RuleService(rules=repo)
    rule = _rule(Citation(document="plan.pdf", page=1), review_status=ReviewStatus.APPROVED)

    with pytest.raises(ValueError, match="approved"):
        await service.record_extracted([rule])

    assert await repo.list() == []
