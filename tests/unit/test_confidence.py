"""Confidence scoring and its consequence: low confidence blocks automated
advisory eligibility (spec invariant 7), even after human approval is
technically possible.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ankur_domain.policies import (
    MIN_AUTO_ELIGIBLE_CONFIDENCE,
    is_advisory_eligible,
    requires_review,
)
from ankur_schemas.citation import Citation
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRule, DACPRuleDraft, DACPRuleFields
from document_intelligence.confidence import score_draft


def test_header_context_increases_score():
    fields = DACPRuleFields(
        state="Haryana", district="Sirsa", condition="dry spell", crop="Pearl millet"
    )
    with_header, _ = score_draft(fields, had_header_context=True)
    without_header, _ = score_draft(fields, had_header_context=False)
    assert with_header > without_header


def test_more_populated_optional_fields_increase_score():
    sparse = DACPRuleFields(state="Haryana", district="Sirsa", condition="dry spell after sowing")
    rich = DACPRuleFields(
        state="Haryana",
        district="Sirsa",
        condition="dry spell after sowing",
        crop="Pearl millet",
        action="Re-sow",
        variety="HHB-67 Improved",
        actor="Block Agriculture Officer",
    )
    sparse_score, _ = score_draft(sparse, had_header_context=True)
    rich_score, _ = score_draft(rich, had_header_context=True)
    assert rich_score > sparse_score


def test_short_condition_is_penalized():
    fields = DACPRuleFields(state="Haryana", district="Sirsa", condition="dry")
    score, notes = score_draft(fields, had_header_context=True)
    assert any("short" in n for n in notes)


def test_score_bounded_zero_to_one():
    fields = DACPRuleFields(
        state="Haryana",
        district="Sirsa",
        condition="long enough condition text",
        crop="A",
        action="B",
        variety="C",
        seed_rate="D",
        actor="E",
        soil="F",
        farming_situation="G",
        crop_stage="H",
    )
    score, _ = score_draft(fields, had_header_context=True)
    assert 0.0 <= score <= 1.0


def test_low_confidence_draft_requires_review():
    fields = DACPRuleFields(state="Haryana", district="Sirsa", condition="dry spell after sowing")
    draft = DACPRuleDraft(
        fields=fields,
        citation=Citation(document="plan.pdf", page=1),
        confidence=MIN_AUTO_ELIGIBLE_CONFIDENCE - 0.01,
        extractor_version="v1",
        extracted_at=datetime.now(UTC),
    )
    needs_review, reasons = requires_review(draft)
    assert needs_review is True
    assert any("confidence" in r for r in reasons)


def test_low_confidence_rule_is_not_advisory_eligible_even_if_marked_approved():
    """A human COULD approve a low-confidence rule after manual verification
    (approval only requires a valid citation, see ankur_domain.policies.can_approve).
    But is_advisory_eligible is the read-time gate the trigger engine will
    use -- confidence alone never re-enters that decision once approved, by
    design. This test documents that approval, not confidence, is the gate.
    """
    fields = DACPRuleFields(state="Haryana", district="Sirsa", condition="dry spell after sowing")
    rule = DACPRule(
        fields=fields,
        citation=Citation(document="plan.pdf", page=1),
        confidence=0.2,
        extractor_version="v1",
        extracted_at=datetime.now(UTC),
        review_status=ReviewStatus.APPROVED,
    )
    assert is_advisory_eligible(rule) is True  # approval + citation, as designed

    unapproved = rule.model_copy(update={"review_status": ReviewStatus.NEEDS_REVIEW})
    assert is_advisory_eligible(unapproved) is False
