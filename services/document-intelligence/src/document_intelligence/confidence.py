"""Confidence scoring for extracted rule drafts.

Deliberately simple and inspectable -- a weighted count of how much
structural evidence backed the extraction, not a learned model. Every
component is named so a reviewer can see exactly why a rule scored the way
it did (see `DACPRuleDraft.notes`).
"""

from __future__ import annotations

from ankur_schemas.rule import DACPRuleFields

_OPTIONAL_FIELD_WEIGHT = 0.06
_OPTIONAL_FIELDS = (
    "crop",
    "crop_stage",
    "action",
    "variety",
    "seed_rate",
    "actor",
    "soil",
    "farming_situation",
)

_BASE_SCORE = 0.35
_HEADER_CONTEXT_BONUS = 0.20
_SHORT_CONDITION_PENALTY = 0.15
_MIN_CONDITION_CHARS = 12


def score_draft(fields: DACPRuleFields, *, had_header_context: bool) -> tuple[float, list[str]]:
    """Score a draft's fields in [0, 1] and return (score, explanatory notes).

    Composition:
      - base score for having a district + condition at all,
      - + a fixed bonus if the row was mapped using a real table header
        (vs. positional/no-context guessing),
      - + a small amount per populated optional field (more corroborating
        detail = more confidence the row was parsed correctly),
      - - a penalty if the condition text is implausibly short to be a real
        weather-aberration description.
    """
    notes: list[str] = []
    score = _BASE_SCORE

    if had_header_context:
        score += _HEADER_CONTEXT_BONUS
        notes.append("row mapped against a recognized table header")
    else:
        notes.append("no table header context available; fields may be mis-mapped")

    populated = [name for name in _OPTIONAL_FIELDS if getattr(fields, name)]
    score += _OPTIONAL_FIELD_WEIGHT * len(populated)
    if populated:
        notes.append(f"populated optional fields: {', '.join(populated)}")

    if len(fields.condition.strip()) < _MIN_CONDITION_CHARS:
        score -= _SHORT_CONDITION_PENALTY
        notes.append("condition text is unusually short")

    return max(0.0, min(1.0, score)), notes
