"""The join contract between the weather side and the rule base.

`DACPRuleFields.condition` is free prose lifted verbatim from a government PDF
("Normal onset followed by 15-20 day dry spell after sowing"). The trigger
engine produces a *physical state* (soil moisture fraction, consecutive dry
days, a calibrated probability). Prose and physics do not join.

`ConditionCode` is the closed vocabulary both sides target. The extractor
normalizes `condition` into a code; the trigger engine emits the same codes and
nothing else. A code the rule base cannot express is a code the trigger engine
must never emit -- which is what makes "silent if the plan is silent" mechanical
rather than aspirational.

Deliberately a closed enum, unlike `crop`/`variety`/`actor` which stay free
strings (see the comment at the top of `enums.py`). The difference: crop names
vary unboundedly across districts, but the *set of weather aberrations a DACP
can describe* is small and fixed by the agronomy. Closing it is what makes the
join checkable.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ConditionCode(StrEnum):
    """Weather-aberration vocabulary shared by extracted rules and the trigger engine.

    Every member needs a machine-evaluable predicate in
    `trigger_engine.conditions`. Adding a member without a predicate makes the
    rule base claim coverage the engine cannot deliver, so the two are
    unit-tested against each other
    (`tests/unit/test_conditions.py::test_every_condition_code_has_a_predicate`).
    """

    DELAYED_ONSET = "delayed_onset"
    """Monsoon onset later than the local normal by a material margin."""

    DRY_SPELL_AFTER_SOWING = "dry_spell_after_sowing"
    """Normal onset, then a dry spell once the crop is in the ground. The
    flagship Sirsa case: this is the one that causes a farmer to buy seed
    twice."""

    MID_SEASON_DRY_SPELL = "mid_season_dry_spell"
    """A break in the monsoon during vegetative/reproductive growth, away from
    the sowing window."""

    TERMINAL_DROUGHT = "terminal_drought"
    """Moisture deficit late in the season, at grain fill / maturity."""

    UNSEASONAL_RAIN = "unseasonal_rain"
    """Rainfall well above the local climatological norm at a stage where it
    causes damage rather than benefit (e.g. at flowering)."""

    UNMAPPED = "unmapped"
    """The extractor could not normalize this rule's prose to a code. Excluded
    from serving: a rule that cannot be matched must never be matched by
    accident."""


# Codes that may drive an advisory. UNMAPPED is a bookkeeping value, not a
# weather state -- keeping it out of this set is what stops a normalization
# failure from silently becoming a trigger.
EMITTABLE_CONDITION_CODES: frozenset[ConditionCode] = frozenset(
    code for code in ConditionCode if code is not ConditionCode.UNMAPPED
)


class MoistureState(BaseModel):
    """Root-zone water balance state for one block on one day.

    Produced by `trigger_engine.waterbalance`, consumed by
    `trigger_engine.conditions` to decide which `ConditionCode` (if any) holds.

    This is a physical state, not a forecast: every field is derivable from
    observations up to and including `as_of`. Keeping forecast probability out
    of this model is deliberate -- it lets the condition predicates be tested
    against observed weather alone, with no model in the loop.
    """

    model_config = ConfigDict(frozen=True)

    block_id: str
    as_of: date

    soil_moisture_fraction: float = Field(
        ..., ge=0.0, le=1.0, description="Root-zone water content as a fraction of capacity."
    )
    consecutive_dry_days: int = Field(
        ..., ge=0, description="Dry days (< rainy-day threshold) ending at `as_of`."
    )
    days_since_sowing: int | None = Field(
        default=None,
        description=(
            "Days since the sowing anchor. None when no anchor is known -- never inferred, "
            "because an inferred anchor makes the sowing-window conditions unfalsifiable."
        ),
    )
    onset_delay_days: int | None = Field(
        default=None,
        description="Observed onset minus local normal onset. Negative = early. None = not yet.",
    )
    rain_3d_mm: float = Field(..., ge=0.0, description="Trailing 3-day rainfall total.")
    rain_3d_normal_mm: float = Field(
        ..., ge=0.0, description="Climatological 3-day total for this pentad, train-years only."
    )


class DrySpellForecast(BaseModel):
    """A calibrated probability that a dry spell begins within the lead window.

    Deliberately carries the model identity and the reference climatology
    alongside the probability: an audit record that says "0.71" without saying
    which model produced it, against which base rate, cannot be reviewed after
    the fact.
    """

    model_config = ConfigDict(frozen=True)

    block_id: str
    issued_on: date
    lead_days: int = Field(..., ge=1, description="Probability refers to the window [t+1, t+L].")
    probability: float = Field(..., ge=0.0, le=1.0)
    climatological_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Base rate for this block and pentad. The BSS reference."
    )
    model_version: str
