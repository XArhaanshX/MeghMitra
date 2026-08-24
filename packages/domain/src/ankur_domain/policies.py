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
from ankur_schemas.condition import EMITTABLE_CONDITION_CODES, ConditionCode
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


def has_valid_citation(citation: Citation | None, *, page_count: int | None = None) -> bool:
    """A citation is valid only if it names a document and a real page number.

    This is the gate behind the core invariant: "no citation -> no approved rule."

    `page_count` is an optional *tightening*, never a loosening: when the caller
    knows how many pages the source document has, a citation pointing past the
    end is rejected. Omitting it preserves the original behaviour exactly, so no
    existing call site changes meaning.

    Why this exists: `data/fixtures/sirsa_dacp.json` cites pages 37, 38, 41 and
    44 of a document that has 31 pages, and one of those rules is seeded
    `approved`. `page >= 1` alone accepts all four. The ingestion pipeline is
    already safe (`tests/integration/test_ingestion.py` asserts the bound), but
    the *policy* was not, so any other path that builds a rule -- a seed script,
    an importer, a second extractor -- bypassed it. A citation nobody can turn
    to is not a citation.
    """
    if citation is None:
        return False
    if not citation.document.strip():
        return False
    if citation.page < 1:
        return False
    return not (page_count is not None and citation.page > page_count)


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


def can_approve(rule: DACPRule, *, page_count: int | None = None) -> tuple[bool, str | None]:
    """Whether a rule is eligible to move to APPROVED.

    Enforces: no citation -> never approvable, period -- independent of who
    is asking or what confidence says. This is the one check that must never
    be bypassed.

    `page_count` is an optional tightening forwarded to `has_valid_citation`.
    When the source document is known, a page past the end of the file is
    rejected. Omitting it preserves the original behaviour.
    """
    if not has_valid_citation(rule.citation, page_count=page_count):
        if page_count is not None and rule.citation is not None and rule.citation.page > page_count:
            return (
                False,
                f"cannot approve: citation page {rule.citation.page} "
                f"exceeds document page_count {page_count}",
            )
        return False, "cannot approve a rule without a valid citation"
    return True, None


def is_advisory_eligible(rule: DACPRule) -> bool:
    """Whether a rule may drive automated advisory output right now.

    Requires both a human APPROVED status and a valid citation -- belt and
    braces, since review status alone should already imply a citation was
    checked at approval time.
    """
    return rule.review_status == ReviewStatus.APPROVED and has_valid_citation(rule.citation)


def can_emit_advisory(
    rule: DACPRule | None,
    detected: ConditionCode | None,
    *,
    page_count: int | None = None,
) -> tuple[bool, list[str]]:
    """Whether the trigger engine may emit an advisory. The default answer is no.

    This is the read-time counterpart to `can_approve`, and it is where
    objective O1 -- "cite, never invent; silent if the plan is silent" -- stops
    being a slogan and becomes a check. Returns `(may_emit, reasons_to_abstain)`,
    mirroring `requires_review`'s shape so both read the same way.

    Four conditions must all hold. Each corresponds to a way the system could
    otherwise say something it has no authority to say:

    1. A condition was actually detected. No detection -> nothing to advise on.
    2. The detected code is emittable (not UNMAPPED). UNMAPPED means
       normalization *failed*; treating a failure as a match would turn a
       parsing bug into agricultural advice.
    3. A rule was matched and is advisory-eligible -- approved by a human, with
       a valid citation. Confidence is deliberately absent here: it gated entry
       to the review queue, and re-checking it now would override a reviewer who
       already read the source page (see `docs/decisions.md`).
    4. The matched rule's condition code equals the detected one. Guards against
       a caller passing a rule fetched on some other axis (district, crop) and
       assuming the condition matched too.

    `page_count` is forwarded to `has_valid_citation` so a caller that knows the
    source document can reject an out-of-range page at emit time as well as at
    approve time.

    Note this function cannot verify that `source_text` actually appears on the
    cited page -- that needs the document, which the domain layer has no I/O to
    reach. That check belongs in the serving layer, and it is listed as an open
    item in `docs/ml-pipeline.md`.
    """
    reasons: list[str] = []

    if detected is None:
        reasons.append("no condition detected")
    elif detected not in EMITTABLE_CONDITION_CODES:
        reasons.append(f"condition {detected.value!r} is not emittable")

    if rule is None:
        reasons.append("no matching approved rule")
    else:
        if rule.review_status != ReviewStatus.APPROVED:
            reasons.append(f"rule review_status is {rule.review_status.value!r}, not 'approved'")
        if not has_valid_citation(rule.citation, page_count=page_count):
            reasons.append("matched rule has no valid citation")
        if detected is not None and rule.fields.condition_code != detected:
            reasons.append(
                f"rule condition_code {rule.fields.condition_code!r} "
                f"does not match detected {detected.value!r}"
            )

    return (len(reasons) == 0, reasons)
