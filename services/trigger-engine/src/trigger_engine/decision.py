"""Probability -> action, via the cost-loss framework. No learning here either.

A probability is not a decision. "60% chance of a dry spell in week 3" does not
tell a farmer with four acres and no borewell whether to sow on Tuesday. This
module is the translation, and it is deliberately deterministic: given the same
probability and the same cost-loss ratio it always returns the same action, which
is what makes an advisory auditable months later.

THE COST-LOSS MODEL

A decision-maker can pay a cost C to protect against a loss L that occurs only if
the adverse event happens. Writing alpha = C/L, the expected-cost-minimising rule
is to act when p > alpha. That result is standard, it is not tuned, and it has a
useful property for this project: it puts the threshold in the *farmer's* hands
rather than ours. We supply a calibrated probability; alpha encodes their
economics.

For the flagship re-sow case the arithmetic is concrete. C is a second bag of seed
plus the labour to re-sow. L is the value of the lost crop if the spell arrives
and nothing was done. A smallholder for whom a failed season is ruinous has a
small alpha and should be warned early. An irrigated farm that can water through a
spell has a large alpha and should be warned rarely. The same probability, two
different correct answers -- which is exactly why the threshold is a parameter and
not a constant.

This is also why calibration matters more than discrimination here. A model with
excellent ROC-AUC but systematically inflated probabilities crosses alpha too
often and floods the farmer with false alarms. `evaluation.value_curve` is the
metric that measures what this module produces.

HYSTERESIS

The submission commits to SMS that must not double-fire. A raw threshold crossing
flips state whenever the probability jitters across alpha, so a farmer near the
boundary could receive contradictory advice on consecutive days -- which destroys
trust faster than being wrong once. `apply_hysteresis` requires a sustained
crossing before the recommendation changes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from ankur_schemas.condition import ConditionCode


class AdvisoryAction(StrEnum):
    """What the farmer is told to do.

    Deliberately tiny. These are the shapes of decision the DACP's own contingency
    rows support; the *content* (which variety, what seed rate) always comes from
    the matched rule, never from here.
    """

    SOW = "sow"
    """Conditions are adequate. Proceed."""

    WAIT = "wait"
    """Dry-spell risk exceeds the farmer's tolerance. Delay sowing."""

    RE_SOW = "re_sow"
    """The crop is already in and a spell is likely to have damaged it. The DACP
    row supplies the short-duration variety to use."""

    ABSTAIN = "abstain"
    """Say nothing. Either the plan is silent, or the forecast is not usable
    today. The default."""


DEFAULT_COST_LOSS_RATIO: Final[float] = 0.35
"""Fallback alpha when the farmer has not supplied their own economics.

Deliberately below the midpoint: in an asymmetric-loss setting like re-sowing, the
cost of acting unnecessarily (one seed bag) is materially smaller than the cost of
failing to act (a lost season). A default above 0.5 would be biased toward
inaction in a way most smallholders would not choose for themselves.

A default, not a recommendation. `docs/ml-pipeline.md` lists per-farmer alpha
elicitation as an open question, and the value curve is reported across the whole
range precisely so nobody has to trust this number."""

HYSTERESIS_CYCLES: Final[int] = 2
"""Consecutive cycles a threshold crossing must persist before advice changes."""

PROBABILITY_DRIVEN_CONDITIONS: Final[frozenset[ConditionCode]] = frozenset(
    {ConditionCode.DRY_SPELL_AFTER_SOWING, ConditionCode.MID_SEASON_DRY_SPELL}
)
"""Conditions whose action `decide` is entitled to choose.

Everything in this module reasons about *one* quantity: the probability that a
dry spell begins within the lead window. `WAIT` means "dry-spell risk exceeds
your tolerance"; `RE_SOW` means "a spell is likely to have damaged the crop".
Neither sentence is about rain, and neither is about onset.

This set exists because the end-to-end path made that implicit assumption
reachable and then violated it. Once real DACP rules were joined in, an
`UNSEASONAL_RAIN` detection -- a *flood* row, whose plan text says "Drainage, if
depth of standing water is > 5-6 cm" -- was handed to `decide`, which saw a
dry-spell probability of 0.54, saw the crop was sown, and returned `RE_SOW`.
Telling a farmer to buy seed again because their field is under water is the
exact failure this product exists to prevent, and it arrived not from a bad model
but from routing a condition through a decision rule that was never about it.

`TERMINAL_DROUGHT` is deliberately absent even though it is a moisture deficit:
its DACP response is harvest and fodder management, not re-sowing, and re-sowing
at maturity is agronomically meaningless.

Conditions outside this set are detected, counted, and abstained on with a stated
reason. They are not unservable in principle -- their plan rows are perfectly
good advice, and the condition is *observed* rather than forecast, so no
threshold is needed to act on them. Serving them needs an advisory action that
means "the plan's row applies", which is a change to what a Block Agriculture
Officer sees and belongs to the team, not to a wiring commit. See
`docs/ml-pipeline.md`."""


@dataclass(frozen=True, slots=True)
class DecisionInput:
    """Everything needed to turn one probability into one action."""

    probability: float
    cost_loss_ratio: float = DEFAULT_COST_LOSS_RATIO
    crop_already_sown: bool = False
    days_since_sowing: int | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    """An action plus the arithmetic that produced it.

    `threshold` and `margin` are carried so an audit record can answer "why did
    this fire?" without re-running the model. A decision that records only its
    output cannot be reviewed after the weather has resolved.
    """

    action: AdvisoryAction
    probability: float
    threshold: float
    reason: str

    @property
    def margin(self) -> float:
        """How far past the threshold the probability sat. Negative means below.

        Useful for triage: a trigger that fired at margin 0.01 deserves more
        scrutiny than one that fired at 0.30.
        """
        return self.probability - self.threshold


def optimal_threshold(cost_loss_ratio: float) -> float:
    """The expected-cost-minimising probability threshold: p* = alpha.

    A one-line function on purpose. It is *named* rather than inlined because it is
    a real result from decision theory and not an arbitrary cutoff, and naming it
    makes every call site say so.
    """
    if not 0.0 < cost_loss_ratio < 1.0:
        raise ValueError(f"cost_loss_ratio must lie in (0, 1), got {cost_loss_ratio}")
    return cost_loss_ratio


def decide(inputs: DecisionInput) -> Decision:
    """Turn a calibrated probability into an action.

    Branches on whether the crop is already in the ground, because that changes
    which decisions are even available:

      * not yet sown -- the choice is SOW or WAIT. Waiting is cheap and reversible.
      * already sown -- waiting is meaningless, the crop is committed. The choice
        is RE_SOW or nothing, and it is viable only while re-sowing still leaves
        enough season for the crop to mature.

    Returns ABSTAIN rather than raising when the probability is unusable, since
    silence is always a valid output for this system.
    """
    if not 0.0 <= inputs.probability <= 1.0:
        return Decision(
            action=AdvisoryAction.ABSTAIN,
            probability=inputs.probability,
            threshold=float("nan"),
            reason=f"probability {inputs.probability} outside [0, 1]",
        )

    threshold = optimal_threshold(inputs.cost_loss_ratio)

    if inputs.probability <= threshold:
        return Decision(
            action=AdvisoryAction.ABSTAIN if inputs.crop_already_sown else AdvisoryAction.SOW,
            probability=inputs.probability,
            threshold=threshold,
            reason=(
                f"p={inputs.probability:.3f} at or below threshold {threshold:.3f}; "
                "no contingency action indicated"
            ),
        )

    if inputs.crop_already_sown:
        return Decision(
            action=AdvisoryAction.RE_SOW,
            probability=inputs.probability,
            threshold=threshold,
            reason=(
                f"p={inputs.probability:.3f} exceeds threshold {threshold:.3f} "
                f"with crop sown {inputs.days_since_sowing} days ago"
            ),
        )

    return Decision(
        action=AdvisoryAction.WAIT,
        probability=inputs.probability,
        threshold=threshold,
        reason=f"p={inputs.probability:.3f} exceeds threshold {threshold:.3f} before sowing",
    )


def apply_hysteresis(
    decisions: Sequence[Decision], *, cycles: int = HYSTERESIS_CYCLES
) -> list[Decision]:
    """Suppress advice changes that have not persisted for `cycles` runs.

    Without this, a probability oscillating around alpha produces WAIT, SOW, WAIT,
    SOW on consecutive days. Each message is individually defensible and the
    sequence is worthless -- and, given the submission's SMS commitment, expensive
    and trust-destroying.

    The rule: a new action must appear `cycles` times in a row before it takes
    effect. Until then the previous action stands, with its reason annotated so the
    audit log shows the suppression rather than hiding it.

    Note the asymmetry this creates: the system is slower to *change its mind* than
    to speak for the first time. That is the correct bias for advisories a farmer
    acts on with money.
    """
    if not decisions:
        return []

    stabilized = [decisions[0]]
    current = decisions[0].action
    pending: AdvisoryAction | None = None
    pending_count = 0

    for decision in decisions[1:]:
        if decision.action == current:
            pending, pending_count = None, 0
            stabilized.append(decision)
            continue

        if decision.action == pending:
            pending_count += 1
        else:
            pending, pending_count = decision.action, 1

        if pending_count >= cycles:
            current = decision.action
            pending, pending_count = None, 0
            stabilized.append(decision)
        else:
            stabilized.append(
                Decision(
                    action=current,
                    probability=decision.probability,
                    threshold=decision.threshold,
                    reason=(
                        f"{decision.reason} [held at {current.value}: "
                        f"{decision.action.value} seen {pending_count}/{cycles} cycles]"
                    ),
                )
            )

    return stabilized


def seed_demand_quintals(
    hectares: float,
    trigger_probability: float,
    seed_rate_kg_per_ha: float,
    *,
    safety_factor: float = 1.2,
) -> float:
    """Expected seed to pre-position for a block, in quintals (100 kg).

        quintals = hectares * p(trigger) * seed_rate * safety_factor / 100

    This is objective O4, the Block Agriculture Officer's output. Multiplying area
    by probability gives *expected* demand -- the right quantity for a stocking
    decision, where the cost of holding surplus seed sits far below the cost of a
    stock-out during a re-sowing window.

    `seed_rate_kg_per_ha` must come from the matched DACP rule, never from general
    agronomic knowledge. Note `seed_rate` is null in every rule of the current
    Sirsa fixture, so this function has no live inputs yet: callers must treat a
    missing seed rate as a reason to report area and probability alone, rather than
    substituting a plausible number.
    """
    if seed_rate_kg_per_ha <= 0:
        raise ValueError("seed_rate_kg_per_ha must be positive; a missing rate is not zero")
    return hectares * trigger_probability * seed_rate_kg_per_ha * safety_factor / 100.0
