"""Draft -> validated rule: routing to pending vs. needs_review.

Covers spec invariant 5 (invalid/ambiguous extraction -> needs_review).
Extraction must NEVER assign `approved` -- only a human review step may.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ankur_schemas.citation import Citation
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRuleDraft, DACPRuleFields
from document_intelligence.validator import validate_draft


def _draft(**field_overrides) -> DACPRuleDraft:
    fields = DACPRuleFields(
        district="Sirsa",
        condition="15-20 day dry spell after sowing",
        crop="Pearl millet",
        action="Re-sow",
        variety="HHB-67 Improved",
        actor="Block Agriculture Officer",
        **field_overrides,
    )
    return DACPRuleDraft(
        fields=fields,
        citation=Citation(document="HAR16-Sirsa-30-06-2011.pdf", page=37, source_text="..."),
        confidence=0.94,
        extractor_version="document-intelligence/0.1.0",
        extracted_at=datetime.now(UTC),
    )


def test_high_confidence_well_cited_draft_is_pending_not_approved():
    """Extraction never auto-approves, even when everything looks correct."""
    rule = validate_draft(_draft())

    assert rule.review_status == ReviewStatus.PENDING
    assert rule.citation.document == "HAR16-Sirsa-30-06-2011.pdf"


def test_missing_citation_document_forces_needs_review():
    draft = _draft()
    draft = draft.model_copy(update={"citation": Citation(document="", page=1)})

    rule = validate_draft(draft)

    assert rule.review_status == ReviewStatus.NEEDS_REVIEW
    assert any("citation" in note for note in rule.notes)


def test_low_confidence_forces_needs_review():
    draft = _draft()
    draft = draft.model_copy(update={"confidence": 0.4})

    rule = validate_draft(draft)

    assert rule.review_status == ReviewStatus.NEEDS_REVIEW
    assert any("confidence" in note for note in rule.notes)


def test_missing_district_forces_needs_review():
    fields = DACPRuleFields(district="   ", condition="some condition")
    draft = DACPRuleDraft(
        fields=fields,
        citation=Citation(document="HAR16-Sirsa-30-06-2011.pdf", page=1),
        confidence=0.9,
        extractor_version="document-intelligence/0.1.0",
        extracted_at=datetime.now(UTC),
    )

    rule = validate_draft(draft)

    assert rule.review_status == ReviewStatus.NEEDS_REVIEW
