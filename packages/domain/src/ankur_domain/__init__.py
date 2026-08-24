"""Ankur domain layer: invariants, repository ports, and services.

No I/O lives here directly -- `policies` is pure functions, `repositories`
are `Protocol` ports, and `services` orchestrate the two against whatever
repository implementation is injected (Postgres in `apps/api`, in-memory in
`ankur_domain.memory` for tests/fixtures).
"""

from ankur_domain.policies import (
    MIN_AUTO_ELIGIBLE_CONFIDENCE,
    can_approve,
    has_valid_citation,
    initial_review_status,
    is_advisory_eligible,
    requires_review,
)
from ankur_domain.services import (
    DocumentNotFoundError,
    DocumentService,
    ReviewService,
    RuleNotApprovableError,
    RuleNotFoundError,
    RuleService,
)

__all__ = [
    "MIN_AUTO_ELIGIBLE_CONFIDENCE",
    "can_approve",
    "has_valid_citation",
    "initial_review_status",
    "is_advisory_eligible",
    "requires_review",
    "DocumentService",
    "RuleService",
    "ReviewService",
    "DocumentNotFoundError",
    "RuleNotFoundError",
    "RuleNotApprovableError",
]
