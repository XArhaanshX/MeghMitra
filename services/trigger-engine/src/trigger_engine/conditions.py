"""Moisture state -> `ConditionCode`. Deterministic, and the default answer is None.

This module is where physics meets the government's vocabulary. It contains no
model and no learned parameters: given a `MoistureState`, each predicate is a
plain boolean expression over observable quantities. That matters twice over.
First, it can be tested against observed weather alone, with no model in the loop,
so a failure here is unambiguously a logic error and not a calibration one.
Second, an agronomist can read it -- and will have to, before any of this reaches
a farmer.

DESIGN: PREDICATE REGISTRY, NOT AN IF-CHAIN

Every `ConditionCode` maps to exactly one predicate in `CONDITION_PREDICATES`.
`tests/unit/test_conditions.py` asserts the mapping is total: adding a code to the
enum without adding a predicate fails the suite. Without that, the rule base could
advertise coverage for a condition the engine can never detect, and the gap would
surface only as an advisory that silently never fires.

DESIGN: FIRST MATCH WINS, IN PRIORITY ORDER

Conditions are not mutually exclusive -- a dry spell twenty days after sowing is
both `DRY_SPELL_AFTER_SOWING` and, read loosely, `MID_SEASON_DRY_SPELL`.
`CONDITION_PRIORITY` fixes the order, most specific first, so the result is
deterministic rather than dependent on dictionary iteration. Specific beats
general because the DACP's specific rows carry the actionable detail: the
after-sowing row names a re-sow variety, the generic mid-season row does not.

DESIGN: RETURNS None, NOT A DEFAULT

No predicate matching yields `None`, and `ankur_domain.policies.can_emit_advisory`
turns that into silence. There is deliberately no fallback code, no "closest
match", no nearest-neighbour over the vocabulary. If the plan does not describe
the weather, Ankur has nothing to say, and inventing a nearest match is exactly
the failure mode the product exists to avoid.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from ankur_geo import DEFAULT_CONDITION_THRESHOLDS, ConditionThresholds
from ankur_schemas.condition import ConditionCode, MoistureState

from trigger_engine.config import (
    DRY_SPELL_MIN_DAYS,
    LOW_SOIL_MOISTURE_FRACTION,
    UNSEASONAL_RAIN_RATIO,
)

ConditionPredicate = Callable[[MoistureState, ConditionThresholds], bool]


def is_delayed_onset(
    state: MoistureState, thresholds: ConditionThresholds = DEFAULT_CONDITION_THRESHOLDS
) -> bool:
    """Monsoon onset later than the local normal by more than three weeks.

    Reads the Sirsa plan's own wording ("Delayed onset of monsoon by more than 3
    weeks") rather than a threshold of our choosing.

    `onset_delay_days is None` means onset has not been declared yet and returns
    False. That is the conservative direction: an undeclared onset is not evidence
    of a delayed one, and Ankur does not declare onset itself -- only IMD does.
    """
    if state.onset_delay_days is None:
        return False
    return state.onset_delay_days > thresholds.delayed_onset_days


def is_dry_spell_after_sowing(
    state: MoistureState, thresholds: ConditionThresholds = DEFAULT_CONDITION_THRESHOLDS
) -> bool:
    """The flagship case: a dry spell striking a crop already in the ground.

    Three things must hold together:

      1. A sowing anchor exists. Never inferred -- an inferred sowing date makes
         the condition unfalsifiable, and this is the condition that tells a farmer
         to spend money on seed a second time.
      2. We are inside the re-sowing window. Past roughly 30 days re-sowing is no
         longer agronomically viable, and the advice would be worse than useless.
      3. The dry spell has run for the Sirsa plan's own 15-20 day band. The Sirsa
         wording is "Normal onset followed by 15-20 days dry spell after sowing" --
         a spell shorter than 15 days has not yet reached what the plan describes,
         and past 20 days the plan's re-sow advice no longer applies either (by
         then the window has usually closed some other way). The soil must also be
         genuinely dry.

    The soil-moisture check is the important second half of (3). A dry spell over
    a wet profile is a meteorological event, not an agricultural one -- the crop
    is fine, and firing a re-sow advisory would cost a farmer a seed bag for
    nothing. Requiring both the rainfall deficit and the soil-moisture deficit is
    what makes this an agricultural trigger rather than a rainfall counter.
    """
    if state.days_since_sowing is None:
        return False
    if not 0 <= state.days_since_sowing <= thresholds.sowing_window_days:
        return False
    return (
        thresholds.dry_spell_after_sowing_min_days
        <= state.consecutive_dry_days
        <= thresholds.dry_spell_after_sowing_max_days
        and state.soil_moisture_fraction < LOW_SOIL_MOISTURE_FRACTION
    )


def is_mid_season_dry_spell(
    state: MoistureState, thresholds: ConditionThresholds = DEFAULT_CONDITION_THRESHOLDS
) -> bool:
    """A monsoon break during vegetative or reproductive growth.

    The general case, checked after the after-sowing one so the more specific
    condition claims the day first. Excludes the late-season window, which
    `is_terminal_drought` handles -- the same weather calls for different action at
    grain fill than at tillering, and the DACP tables are organised that way.
    """
    if state.as_of.timetuple().tm_yday >= thresholds.terminal_drought_doy_start:
        return False
    return (
        state.consecutive_dry_days >= DRY_SPELL_MIN_DAYS
        and state.soil_moisture_fraction < LOW_SOIL_MOISTURE_FRACTION
    )


def is_terminal_drought(
    state: MoistureState, thresholds: ConditionThresholds = DEFAULT_CONDITION_THRESHOLDS
) -> bool:
    """Moisture deficit late in the season, at grain fill or maturity.

    Split from the mid-season case because the agronomy diverges sharply:
    mid-season the response is life-saving irrigation or a contingency crop;
    terminal, it is harvest management and fodder planning. Same physics, different
    DACP row, different advice.
    """
    if state.as_of.timetuple().tm_yday < thresholds.terminal_drought_doy_start:
        return False
    return (
        state.consecutive_dry_days >= DRY_SPELL_MIN_DAYS
        and state.soil_moisture_fraction < LOW_SOIL_MOISTURE_FRACTION
    )


def is_unseasonal_rain(
    state: MoistureState, thresholds: ConditionThresholds = DEFAULT_CONDITION_THRESHOLDS
) -> bool:
    """Rainfall far above the pentad norm, where excess causes damage.

    A ratio against the local climatological normal rather than an absolute
    millimetre threshold, so the same rule travels between a block averaging 400 mm
    a season and one averaging 900 mm. An absolute threshold would fire constantly
    in the wet block and never in the dry one.

    Guards against a zero normal: early-June pentads can have a climatological mean
    of zero in arid blocks, and dividing by it would make any rain at all
    infinitely unseasonal.

    Takes `thresholds` only for signature parity with the rest of
    `CONDITION_PREDICATES` -- unseasonal rain is not one of the day-count/day-band
    conditions `ConditionThresholds` parameterises.
    """
    if state.rain_3d_normal_mm <= 0.0:
        return False
    return state.rain_3d_mm > UNSEASONAL_RAIN_RATIO * state.rain_3d_normal_mm


CONDITION_PREDICATES: Final[dict[ConditionCode, ConditionPredicate]] = {
    ConditionCode.DELAYED_ONSET: is_delayed_onset,
    ConditionCode.DRY_SPELL_AFTER_SOWING: is_dry_spell_after_sowing,
    ConditionCode.MID_SEASON_DRY_SPELL: is_mid_season_dry_spell,
    ConditionCode.TERMINAL_DROUGHT: is_terminal_drought,
    ConditionCode.UNSEASONAL_RAIN: is_unseasonal_rain,
}
"""Every emittable code, mapped to its predicate.

`UNMAPPED` is absent on purpose: it is a bookkeeping value meaning "normalization
failed", not a weather state, so nothing should ever detect it."""


CONDITION_PRIORITY: Final[tuple[ConditionCode, ...]] = (
    ConditionCode.DRY_SPELL_AFTER_SOWING,
    ConditionCode.DELAYED_ONSET,
    ConditionCode.UNSEASONAL_RAIN,
    ConditionCode.TERMINAL_DROUGHT,
    ConditionCode.MID_SEASON_DRY_SPELL,
)
"""Evaluation order, most specific first.

After-sowing leads because it is the only one carrying a re-sow decision and a
named variety. Mid-season trails because it is the catch-all: anything reaching it
has already failed every more specific test.
"""


def detect_condition(
    state: MoistureState, thresholds: ConditionThresholds = DEFAULT_CONDITION_THRESHOLDS
) -> ConditionCode | None:
    """The first condition in priority order whose predicate holds, else None.

    Args:
        state: Observed moisture state for one block on one day.
        thresholds: Numeric thresholds the predicates read. Defaults to
            `ankur_geo.DEFAULT_CONDITION_THRESHOLDS`, reproducing today's
            Sirsa/Haryana-derived behaviour exactly.

    Returns:
        A `ConditionCode`, or `None` when the weather matches nothing the plan
        describes. `None` is a normal, frequent, *correct* outcome -- most days in
        a monsoon are unremarkable -- and it is what `can_emit_advisory` converts
        into silence.
    """
    for code in CONDITION_PRIORITY:
        if CONDITION_PREDICATES[code](state, thresholds):
            return code
    return None


def explain_condition(
    state: MoistureState, thresholds: ConditionThresholds = DEFAULT_CONDITION_THRESHOLDS
) -> dict[str, bool]:
    """Evaluate every predicate, for the audit log and the review UI.

    `detect_condition` returns a single winner, which is what the decision path
    needs but is unhelpful when a reviewer asks why a near-miss did not fire. This
    returns the full picture, so an audit record can show that (say) the dry spell
    was long enough but the soil was still wet.

    Diagnostic only -- nothing branches on this.
    """
    return {
        code.value: predicate(state, thresholds)
        for code, predicate in CONDITION_PREDICATES.items()
    }
