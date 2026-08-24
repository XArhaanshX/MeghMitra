"""Business invariants of the Ankur domain.

These are pure functions with no I/O -- deliberately, so the two core
guarantees of the system can be unit-tested without a database or a PDF:

    1. No citation -> a rule can never be approved.
    2. Confidence below MIN_AUTO_ELIGIBLE_CONFIDENCE -> not eligible for
       automated advisory output, even if a human later approves it.

Both `document_intelligence` (validation step) and `apps/api` (approve
endpoint) call these instead of re-implementing the rule.
"""

from __future__ import annotations

from ankur_schemas.citation import Citation
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRule, DACPRuleDraft

MIN_AUTO_ELIGIBLE_CONFIDENCE = 0.85
"""Below this, a draft is routed to needs_review regardless of how complete
extraction looked. This does NOT block human approval -- a reviewer can
still approve a low-confidence rule after reading the source page -- it
only blocks the extractor from proposing pending-but-unreviewed rules with
false confidence."""

REQUIRED_FIELDS_FOR_CITATION = ("document",)
"""Citation fields that must be non-empty for a citation to count as valid."""


def has_valid_citation(citation: Citation | None) -> bool:
    """A citation is valid only if it names a document and a positive page number.

    This is the gate behind the core invariant: "no citation -> no approved rule."
    """
    if citation is None:
        return False
    return bool(citation.document.strip()) and citation.page >= 1


def requires_review(draft: DACPRuleDraft) -> tuple[bool, list[str]]:
    """Decide whether a draft must be routed to human review, and why.

    Returns (needs_review, reasons). A draft needs review when:
      - it has no valid citation (never eligible for auto-approval),
      - its confidence is below the auto-eligible threshold,
      - its condition or district field is missing/blank (required fields).
    """
    reasons: list[str] = []

    if not has_valid_citation(draft.citation):
        reasons.append("missing or invalid citation")

    if draft.confidence < MIN_AUTO_ELIGIBLE_CONFIDENCE:
        reasons.append(
            f"confidence {draft.confidence:.2f} below auto-eligible threshold "
            f"{MIN_AUTO_ELIGIBLE_CONFIDENCE:.2f}"
        )

    if not draft.fields.district.strip():
        reasons.append("missing district")

    if not draft.fields.condition.strip():
        reasons.append("missing condition")

    return (len(reasons) > 0, reasons)


def initial_review_status(draft: DACPRuleDraft) -> tuple[ReviewStatus, list[str]]:
    """The review status a freshly-extracted draft should start at.

    Extraction NEVER produces `APPROVED` -- only a human reviewer can.
    """
    needs_review, reasons = requires_review(draft)
    status = ReviewStatus.NEEDS_REVIEW if needs_review else ReviewStatus.PENDING
    return status, reasons


def can_approve(rule: DACPRule) -> tuple[bool, str | None]:
    """Whether a rule is eligible to move to APPROVED.

    Enforces: no citation -> never approvable, period -- independent of who
    is asking or what confidence says. This is the one check that must never
    be bypassed.
    """
    if not has_valid_citation(rule.citation):
        return False, "cannot approve a rule without a valid citation"
    return True, None


def is_advisory_eligible(rule: DACPRule) -> bool:
    """Whether a rule may drive automated advisory output right now.

    Requires both a human APPROVED status and a valid citation -- belt and
    braces, since review status alone should already imply a citation was
    checked at approval time.
    """
    return rule.review_status == ReviewStatus.APPROVED and has_valid_citation(rule.citation)
