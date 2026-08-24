"""Draft -> validated `DACPRule`.

Applies schema validation (already enforced by pydantic on construction)
plus the domain invariants in `ankur_domain.policies`. This is the only
place a draft becomes a persisted-shape `DACPRule` with a review status --
extraction never assigns `APPROVED` itself.
"""

from __future__ import annotations

from ankur_domain.policies import initial_review_status
from ankur_schemas.rule import DACPRule, DACPRuleDraft


def validate_draft(draft: DACPRuleDraft) -> DACPRule:
    status, reasons = initial_review_status(draft)
    notes = list(draft.notes)
    notes.extend(reasons)

    return DACPRule(
        document_id=draft.document_id,
        fields=draft.fields,
        citation=draft.citation,
        confidence=draft.confidence,
        extractor_version=draft.extractor_version,
        extracted_at=draft.extracted_at,
        review_status=status,
        notes=notes,
    )


def validate_drafts(drafts: list[DACPRuleDraft]) -> list[DACPRule]:
    return [validate_draft(d) for d in drafts]
