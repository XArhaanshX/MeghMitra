"""Condition-detection thresholds: a per-plan parameter, not a national constant.

`trigger_engine.config` hardcoded five numbers -- `DELAYED_ONSET_DAYS`,
`SOWING_WINDOW_DAYS`, the dry-spell-after-sowing day band, and
`TERMINAL_DROUGHT_DOY_START` -- each documented in its own module as
transcribed from one document: "read straight off the Sirsa plan's own
wording." `ConditionThresholds` is the parameter object that replaces them,
so `trigger_engine.conditions`' predicates can eventually take a per-district
value sourced from that district's own DACP text (a `document-intelligence`
extraction task, not addressed here) while every predicate that has not been
given an override keeps behaving exactly as it does today.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConditionThresholds:
    """Numeric thresholds the condition predicates in `trigger_engine.conditions`
    consume. Defaults reproduce today's Sirsa/Haryana-derived behaviour
    exactly -- this object only adds the *ability* to override per plan; it
    changes no default."""

    delayed_onset_days: int = 21
    """Monsoon onset later than normal by more than this many days counts as
    `DELAYED_ONSET`. Sirsa plan wording: "more than 3 weeks"."""

    sowing_window_days: int = 30
    """Days after which re-sowing is no longer considered agronomically
    viable."""

    dry_spell_after_sowing_min_days: int = 15
    dry_spell_after_sowing_max_days: int = 20
    """The Sirsa plan's own day band for "15-20 days dry spell after sowing".
    `trigger_engine.config` defined these but `conditions.is_dry_spell_after_sowing`
    never read them -- Phase 5 wires them in alongside this object landing."""

    terminal_drought_doy_start: int = 250
    """Day-of-year (non-leap) at which the terminal-drought window begins,
    roughly September 7 -- tied to a kharif (JJAS) crop calendar."""


DEFAULT_CONDITION_THRESHOLDS = ConditionThresholds()
"""Identical to the values `trigger_engine.config` hardcoded before this
module existed."""
