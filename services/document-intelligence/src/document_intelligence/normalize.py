"""Condition prose -> `ConditionCode`. The join contract, implemented.

WHY THIS MODULE EXISTS

`ankur_schemas.condition` states the contract plainly: "The extractor normalizes
`condition` into a code; the trigger engine emits the same codes and nothing
else." Until now only `apps/api/app/seed.py` assigned a code, by hand, for three
demonstration rules. Every rule the extractor produced left `condition_code` at
`None`, so `policies.can_emit_advisory`'s fourth check --

    rule.fields.condition_code != detected  ->  abstain

-- could never pass for an extracted rule. The rule base and the weather model
were two halves of a system with nothing between them. This module is that
between.

WHY KEYWORDS AND NOT A CLASSIFIER

A learned classifier is the obvious reach here and the wrong one, for three
reasons specific to this problem:

  1. There is no labelled data. Building a training set means an agronomist
     hand-labelling thousands of conditions -- which, once done, is the mapping
     itself, and a lookup beats a model trained on it.
  2. The vocabulary is closed and small. ICAR-CRIDA writes all ~650 plans from
     one template with a fixed set of aberrations. The variation is in wording
     ("delayed onset" / "late onset" / "delay by 4 weeks"), not in concept.
  3. A wrong code is worse than no code. `UNMAPPED` is inert -- it is excluded
     from `EMITTABLE_CONDITION_CODES`, so it abstains. A confident
     misclassification instead routes a farmer the wrong government action. A
     keyword table fails visibly and is fixed by adding a phrase; a classifier
     fails quietly at some confidence threshold nobody can audit.

So: an ordered table of phrases, and `UNMAPPED` when nothing matches. Every
decision is traceable to the phrase that caused it, which is what
`explain_normalization` returns for the review UI.

ORDERING IS THE SEMANTICS

Conditions overlap in prose exactly as they do in physics. "Normal onset
followed by 15-20 days dry spell after sowing" is a dry spell and is mid-season
by the calendar; the row that names a re-sowing variety is the after-sowing one.
`_PRIORITY` fixes the order, most specific first, mirroring
`trigger_engine.conditions.CONDITION_PRIORITY`. The two orderings must agree --
if the extractor calls a row `MID_SEASON_DRY_SPELL` and the engine detects
`DRY_SPELL_AFTER_SOWING` for the same weather, the join silently never fires and
the system is merely quiet rather than visibly broken. They are duplicated
rather than shared because `document_intelligence` and `trigger_engine` are
siblings that must not import each other (see `docs/architecture.md`);
`tests/unit/test_normalize.py` asserts they stay in step.
"""

from __future__ import annotations

import re
from typing import Final

from ankur_schemas.condition import ConditionCode

# Phrase tables, one per code. Matched case-insensitively against the condition
# text after whitespace and hyphen normalization, so "mid-season", "mid season"
# and "mid  season" are one phrase.
#
# Entries are regular expressions, but deliberately shallow ones -- alternations
# and optional plurals only. Anything needing a lookahead to express belongs in
# a comment explaining why, not in a regex nobody can read.

_DRY_SPELL_AFTER_SOWING: Final[tuple[str, ...]] = (
    r"dry spell after sowing",
    r"after sowing",
    r"normal onset.{0,60}dry spell",
    r"poor germination",
    r"crop stand",
    r"re ?sowing",
    r"gap filling",
    r"establishment failure",
    r"seedling mortality",
)
"""The flagship case, and the reason the priority order exists.

`after sowing` alone is enough: in a DACP contingency table the phrase appears
only in rows about a crop already in the ground. `re-sowing` and `poor
germination` catch the rows that describe the consequence instead of the cause,
which several states do."""

_DELAYED_ONSET: Final[tuple[str, ...]] = (
    r"delayed onset",
    r"delay(ed)? (in |of )?(the )?(monsoon|onset)",
    r"late onset",
    r"delay by \d+ ?weeks?",
    r"onset.{0,20}delay",
    r"monsoon.{0,20}(late|delayed)",
)
"""Onset later than the local normal.

`delay by N weeks` is the template's own sub-row wording -- the Sirsa plan runs
"Delay by 2 weeks (July 3rd week)" through "Delay by 8 weeks (Sept. 1st week)"
as separate rows under one delayed-onset heading."""

_TERMINAL_DROUGHT: Final[tuple[str, ...]] = (
    r"terminal drought",
    r"early withdrawal",
    r"late season drought",
    r"withdrawal of (the )?monsoon",
    r"at maturity",
    r"grain fill",
)
"""Deficit at grain fill or maturity. Checked before the mid-season phrases
because "terminal drought (long dry spell)" is both by wording and terminal by
agronomy -- and the two call for different action, harvest management rather
than life-saving irrigation."""

_UNSEASONAL_RAIN: Final[tuple[str, ...]] = (
    r"unseasonal rain",
    r"unusual rain",
    r"untimely rain",
    r"excess(ive)? rain",
    r"heavy rain",
    r"continuous rain",
    r"high rainfall",
    r"flood",
    r"water ?logging",
    r"hail ?storm",
)
"""Rain where rain is the damage. `flood` and `waterlogging` are included
because the template's "2.2 Unusual rains" section words the same condition both
ways."""

_MID_SEASON_DRY_SPELL: Final[tuple[str, ...]] = (
    r"mid ?season",
    r"long dry spell",
    r"dry spell",
    r"rainless period",
    r"consecutive \d+ ?weeks",
    r"break in monsoon",
    r"monsoon break",
    r"prolonged dry",
)
"""The catch-all dry-spell case. Last in priority: anything reaching it has
already failed the after-sowing and terminal tests, so a bare "dry spell" with
no stage information lands here."""


_PRIORITY: Final[tuple[tuple[ConditionCode, tuple[str, ...]], ...]] = (
    (ConditionCode.DRY_SPELL_AFTER_SOWING, _DRY_SPELL_AFTER_SOWING),
    (ConditionCode.DELAYED_ONSET, _DELAYED_ONSET),
    (ConditionCode.UNSEASONAL_RAIN, _UNSEASONAL_RAIN),
    (ConditionCode.TERMINAL_DROUGHT, _TERMINAL_DROUGHT),
    (ConditionCode.MID_SEASON_DRY_SPELL, _MID_SEASON_DRY_SPELL),
)
"""Evaluation order, most specific first.

Mirrors `trigger_engine.conditions.CONDITION_PRIORITY`. Kept in the same order
for the reason given in the module docstring: a disagreement between the two
does not raise, it just makes the join miss."""

_COMPILED: Final[tuple[tuple[ConditionCode, tuple[re.Pattern[str], ...]], ...]] = tuple(
    (code, tuple(re.compile(pattern) for pattern in patterns)) for code, patterns in _PRIORITY
)

_WHITESPACE = re.compile(r"\s+")
_HYPHEN = re.compile(r"[‐-―\-]+")


def canonicalize(text: str) -> str:
    """Fold the surface variation the phrase tables should not have to carry.

    Lowercases, collapses whitespace (including the newlines a reassembled cell
    carries), and turns every dash variant into a single space so "mid-season",
    "mid season" and "mid–season" are the same string. Digits and
    parentheses are left alone: "delay by 4 weeks" and "(Aug 1st week)" both
    depend on them.
    """
    folded = _HYPHEN.sub(" ", text.casefold())
    return _WHITESPACE.sub(" ", folded).strip()


def normalize_condition(text: str | None) -> ConditionCode:
    """Map condition prose to the closed vocabulary the trigger engine joins on.

    Args:
        text: The verbatim `condition` cell. May be None or blank.

    Returns:
        The first `ConditionCode` in priority order whose phrase table matches,
        or `ConditionCode.UNMAPPED` when none does.

    `UNMAPPED` is a real answer, not an error. It means "this row says something
    the engine has no predicate for", which is a coverage fact worth measuring --
    and because `UNMAPPED` is excluded from `EMITTABLE_CONDITION_CODES`, a row
    carrying it abstains rather than guessing. Note the distinction the schema
    draws and this function preserves: `None` on the field means normalization
    never ran; `UNMAPPED` means it ran and found nothing.
    """
    if not text or not text.strip():
        return ConditionCode.UNMAPPED

    haystack = canonicalize(text)
    for code, patterns in _COMPILED:
        if any(pattern.search(haystack) for pattern in patterns):
            return code
    return ConditionCode.UNMAPPED


def explain_normalization(text: str | None) -> tuple[ConditionCode, str | None]:
    """Normalize, and say which phrase decided it.

    The review UI needs the reason as much as the answer: a reviewer looking at a
    row coded `TERMINAL_DROUGHT` should be able to see it was the words "early
    withdrawal" that did it, and disagree if the row actually meant something
    else.

    Returns:
        `(code, matched_phrase)`. `matched_phrase` is None when the result is
        `UNMAPPED`.
    """
    if not text or not text.strip():
        return ConditionCode.UNMAPPED, None

    haystack = canonicalize(text)
    for code, patterns in _COMPILED:
        for pattern in patterns:
            if pattern.search(haystack):
                return code, pattern.pattern
    return ConditionCode.UNMAPPED, None
