"""Domain services: orchestrate repositories + policies.

Route handlers in `apps/api` and the CLI in `document_intelligence` should
call these instead of touching repositories or policies directly -- this is
the one place business rules and persistence meet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from ankur_schemas.citation import Citation
from ankur_schemas.document import DocumentMetadata
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRule

from ankur_domain.policies import can_approve
from ankur_domain.repositories import DocumentRepository, RuleRepository


class RuleNotFoundError(LookupError):
    pass


class DocumentNotFoundError(LookupError):
    pass


class RuleNotApprovableError(ValueError):
    pass


@dataclass(slots=True)
class DocumentService:
    documents: DocumentRepository

    async def register(self, document: DocumentMetadata) -> DocumentMetadata:
        return await self.documents.add(document)

    async def get(self, document_id: UUID) -> DocumentMetadata:
        doc = await self.documents.get(document_id)
        if doc is None:
            raise DocumentNotFoundError(str(document_id))
        return doc

    async def list(self) -> list[DocumentMetadata]:
        return await self.documents.list()


@dataclass(slots=True)
class RuleService:
    """Read access to rules, plus the citation lookup that answers
    "why did Ankur produce this recommendation?".
    """

    rules: RuleRepository

    async def get(self, rule_id: UUID) -> DACPRule:
        rule = await self.rules.get(rule_id)
        if rule is None:
            raise RuleNotFoundError(str(rule_id))
        return rule

    async def list(self, *, review_status: ReviewStatus | None = None) -> list[DACPRule]:
        return await self.rules.list(review_status=review_status.value if review_status else None)

    async def citation_for(self, rule_id: UUID) -> Citation:
        rule = await self.get(rule_id)
        return rule.citation

    async def record_extracted(self, rules: list[DACPRule]) -> list[DACPRule]:
        """Persist freshly-extracted rules. Extraction never sets APPROVED --
        `validate_draft` guarantees every incoming rule is PENDING or
        NEEDS_REVIEW, so this is a plain insert, not a review decision."""
        return [await self.rules.add(rule) for rule in rules]


@dataclass(slots=True)
class ReviewService:
    """Human-in-the-loop approve/reject workflow.

    `approve` is the single chokepoint that enforces "no citation -> no
    approved rule" at the persistence boundary, independent of what
    `initial_review_status` decided at extraction time.
    """

    rules: RuleRepository

    async def _get(self, rule_id: UUID) -> DACPRule:
        rule = await self.rules.get(rule_id)
        if rule is None:
            raise RuleNotFoundError(str(rule_id))
        return rule

    async def review_queue(self) -> list[DACPRule]:
        return await self.rules.list(review_status=ReviewStatus.NEEDS_REVIEW.value)

    async def approve(self, rule_id: UUID, *, reviewed_by: str) -> DACPRule:
        rule = await self._get(rule_id)
        ok, reason = can_approve(rule)
        if not ok:
            raise RuleNotApprovableError(reason or "rule is not approvable")
        updated = rule.model_copy(
            update={
                "review_status": ReviewStatus.APPROVED,
                "reviewed_by": reviewed_by,
                "reviewed_at": datetime.now(UTC),
            }
        )
        return await self.rules.update(updated)

    async def reject(
        self, rule_id: UUID, *, reviewed_by: str, reason: str | None = None
    ) -> DACPRule:
        rule = await self._get(rule_id)
        notes = list(rule.notes)
        if reason:
            notes.append(f"rejected: {reason}")
        updated = rule.model_copy(
            update={
                "review_status": ReviewStatus.REJECTED,
                "reviewed_by": reviewed_by,
                "reviewed_at": datetime.now(UTC),
                "notes": notes,
            }
        )
        return await self.rules.update(updated)
