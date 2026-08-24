"""The DACP rule: the central domain object.

A rule is a pre-approved government contingency action, extracted verbatim
(never invented) from a District Agriculture Contingency Plan. Nullable
fields are the norm, not the exception -- DACP documents are inconsistent in
what they specify, and a missing value must stay `null` rather than being
guessed.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ankur_schemas.citation import Citation
from ankur_schemas.enums import ReviewStatus


class DACPRuleFields(BaseModel):
    """The extractable, DACP-specific content of a rule.

    Shared by `DACPRuleDraft` (pre-validation, extractor output) and
    `DACPRule` (post-validation, persisted). Every field except `district`
    and `condition` may legitimately be null -- the source document simply
    may not specify it.
    """

    district: str = Field(..., description="District the plan applies to, e.g. 'Sirsa'.")
    block: str | None = Field(
        default=None, description="Block / locality, if the plan is that granular."
    )
    farming_situation: str | None = Field(
        default=None, description="e.g. 'Irrigated', 'Rainfed - light soil'."
    )
    crop: str | None = None
    soil: str | None = None
    crop_stage: str | None = Field(default=None, description="e.g. 'After sowing', 'Flowering'.")
    condition: str = Field(
        ..., description="The weather aberration / dry-spell condition that triggers this action."
    )
    action: str | None = Field(default=None, description="The pre-approved contingency action.")
    variety: str | None = None
    seed_rate: str | None = Field(
        default=None, description="Kept as text: units and formats vary across DACP documents."
    )
    actor: str | None = Field(
        default=None, description="Who executes the action, e.g. 'Block Agriculture Officer'."
    )


class DACPRuleDraft(BaseModel):
    """Raw extractor output, prior to schema/business-rule validation.

    Distinct from `DACPRule`: a draft has no identity, no persisted review
    status, and has not yet been checked against domain invariants (e.g.
    "no citation -> not eligible for approval"). `RuleValidator` turns a
    draft into a `DACPRule`.
    """

    document_id: UUID | None = Field(
        default=None, description="Source document id, once known (set by the extraction pipeline)."
    )
    fields: DACPRuleFields
    citation: Citation
    confidence: float = Field(..., ge=0.0, le=1.0)
    extractor_version: str
    extracted_at: datetime
    notes: list[str] = Field(
        default_factory=list,
        description="Extractor/validator remarks, e.g. why confidence was reduced.",
    )


class DACPRule(BaseModel):
    """A validated, identified DACP rule as persisted in the database.

    This is the unit the trigger engine will eventually look up. It is
    never mutated by anything other than the review workflow
    (approve/reject) -- extraction always produces a new draft/version.
    """

    id: UUID = Field(default_factory=uuid4)
    document_id: UUID | None = Field(default=None, description="Source document id.")
    fields: DACPRuleFields
    citation: Citation
    confidence: float = Field(..., ge=0.0, le=1.0)
    extractor_version: str
    extracted_at: datetime
    review_status: ReviewStatus = ReviewStatus.PENDING
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    notes: list[str] = Field(default_factory=list)

    @property
    def is_advisory_eligible(self) -> bool:
        """A rule may only drive automated advisory output once a human has
        approved it. This mirrors `ankur_domain.policies.can_auto_approve`
        but is exposed here for cheap, dependency-free checks at read time.
        """
        return self.review_status == ReviewStatus.APPROVED
