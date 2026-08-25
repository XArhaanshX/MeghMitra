"""Where the two halves meet: an ingested rule base plus weather, in, advisories out.

WHY THIS MODULE EXISTS

The repository had both halves of the system and no seam between them.
`document_intelligence` wrote rules to `data/processed/`. `trigger_engine` turned
weather into a calibrated probability and a `ConditionCode`. `emit_advisory` knew
how to combine a rule with a condition -- but took `candidate_rules` as an
argument that nothing supplied, so the combination never happened outside a unit
test.

This module runs the whole path for one district: preprocess the weather, fit the
model ladder out of fold, walk the evaluation season day by day, and at each step
ask whether an advisory may be emitted. It is the smallest thing that can
honestly be called "working".

THE PROBABILITY IS ALWAYS OUT OF FOLD

Every advisory here uses a probability from `CrossValidationResult.out_of_fold` --
made by a model that never saw that row's season. The alternative, fitting once
on everything and predicting the same rows, would make the demo look better and
mean nothing. `scored_positions` exists so the safe probabilities can be joined
back to the rows they describe.

WHAT THIS DOES NOT DO

It does not approve rules. `simulate_reviewer_approval` exists and is separate,
loud, and off by default, because "extraction never self-approves" is the
invariant the whole product rests on. Run without it, every advisory abstains
with "rule review_status is 'needs_review'" -- and that is the system working
correctly, not failing. A rule base no human has reviewed *should* produce
silence.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from ankur_domain.policies import can_approve
from ankur_schemas.condition import ConditionCode, DrySpellForecast
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRule

from trigger_engine.conditions import detect_condition, explain_condition
from trigger_engine.config import COL_BLOCK, COL_DATE, COL_RAIN
from trigger_engine.decision import AdvisoryAction, Decision
from trigger_engine.features import pentad_climatology
from trigger_engine.pipeline import (
    CrossValidationResult,
    emit_advisory,
    moisture_state_from_row,
    prepare_panel,
    run_cross_validation,
)
from trigger_engine.preprocess import season_of
from trigger_engine.rulestore import RuleStore

logger = logging.getLogger(__name__)

DEMO_APPROVER = "demo-reviewer (SIMULATED, not a human)"
"""Stamped into `reviewed_by` by `simulate_reviewer_approval`.

Deliberately unmistakable. If a simulated approval ever reaches a database or a
screen, the string itself says so -- an audit trail that reads "approved by
demo-reviewer (SIMULATED, not a human)" cannot be mistaken for review."""


@dataclass(frozen=True, slots=True)
class AdvisoryOutcome:
    """One block-day's decision, including the ones that said nothing.

    Abstentions are recorded, not discarded. "Why did Ankur stay silent on the
    day my crop failed?" is the question this system will be asked, and it can
    only be answered from a record that kept the silences and their reasons.
    """

    block_id: str
    as_of: date
    detected: ConditionCode | None
    probability: float
    action: AdvisoryAction
    decision: Decision | None
    rule: DACPRule | None
    abstain_reasons: list[str] = field(default_factory=list)
    predicates: dict[str, bool] = field(default_factory=dict)

    @property
    def emitted(self) -> bool:
        return self.action is not AdvisoryAction.ABSTAIN


@dataclass(frozen=True, slots=True)
class DistrictRun:
    """Everything one district's end-to-end run produced."""

    district: str
    lead_days: int
    model_name: str
    brier_skill_score: float
    outcomes: list[AdvisoryOutcome]
    candidate_rule_count: int
    approved_rule_count: int
    verification: list[CrossValidationResult] = field(default_factory=list)

    @property
    def emitted(self) -> list[AdvisoryOutcome]:
        return [outcome for outcome in self.outcomes if outcome.emitted]

    @property
    def detections(self) -> list[AdvisoryOutcome]:
        """Block-days where the physics matched a DACP condition.

        The gap between this and `emitted` is the whole safety story: how often
        the weather said something the plan describes, versus how often Ankur was
        allowed to pass that on.
        """
        return [outcome for outcome in self.outcomes if outcome.detected is not None]


def simulate_reviewer_approval(rules: list[DACPRule], store: RuleStore) -> list[DACPRule]:
    """Return copies of `rules` marked approved, for demonstration only.

    NOT A REVIEW. This exists so the emission path can be exercised before any
    agronomist has looked at the corpus, and for no other purpose. It must never
    be reachable from the API, the ingestion pipeline, or anything that writes to
    a real database.

    What it does *not* do is bypass the citation invariant. Each rule still has to
    pass `ankur_domain.policies.can_approve`, including the page bound -- a rule
    citing page 44 of a 31-page plan is refused here exactly as it would be
    refused from the review endpoint. What is simulated is the human judgement
    about whether the extracted text is faithful; what is not simulated is any
    check a machine can make.

    Returns:
        Only the rules that were approvable. Rules that fail `can_approve` are
        dropped and logged, so the count difference is visible in the report.
    """
    approved: list[DACPRule] = []
    for rule in rules:
        ok, reason = can_approve(rule, page_count=store.page_count_for(rule))
        if not ok:
            logger.debug("not approvable: %s (%s)", rule.id, reason)
            continue
        approved.append(
            rule.model_copy(
                update={
                    "review_status": ReviewStatus.APPROVED,
                    "reviewed_by": DEMO_APPROVER,
                }
            )
        )
    return approved


def _days_since_sowing(as_of: date, sowing_date: date | None) -> int | None:
    """Days since this season's sowing anchor, or None when no anchor was given.

    The anchor's month and day are re-based onto `as_of`'s year, so one supplied
    date serves every season in a multi-season panel. Returns None -- never a
    guess -- when no anchor exists, which is what keeps
    `is_dry_spell_after_sowing` unable to fire on inferred information.
    """
    if sowing_date is None:
        return None
    try:
        anchor = sowing_date.replace(year=as_of.year)
    except ValueError:
        # 29 February in a non-leap year. Fall back to the 28th rather than
        # dropping the anchor: a one-day shift is immaterial to a 30-day window.
        anchor = sowing_date.replace(year=as_of.year, day=28)
    return (as_of - anchor).days


def _rain_3d(panel: pd.DataFrame) -> pd.Series:
    """Trailing 3-day rainfall per block, for the unseasonal-rain predicate."""
    return (
        panel.groupby(COL_BLOCK, observed=True)[COL_RAIN]
        .rolling(window=3, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )


def run_district(
    state: str,
    district: str,
    store: RuleStore,
    observations: pd.DataFrame,
    *,
    lead_days: int = 14,
    cost_loss_ratio: float = 0.20,
    latitude_deg: float | pd.Series | None = None,
    sowing_date: date | None = None,
    onset_delay_days: int | None = None,
    approve_for_demo: bool = False,
) -> DistrictRun:
    """Run the full path for one district and return every decision it made.

    Args:
        state: State the district's plan belongs to. Required, not inferred --
            `district` alone is ambiguous on the real corpus (Bijapur, Balrampur,
            Pratapgarh and Raigarh each name a district in two different states),
            and passing the wrong one would retrieve a different state's
            contingency plan under this district's name.
        district: District to look rules up under.
        store: The ingested rule base.
        observations: Long-format weather (`date`, `block`, `rain_mm`, `tmin_c`,
            `tmax_c`).
        lead_days: Forecast horizon for the dry-spell probability.
        cost_loss_ratio: The BAO's cost of acting divided by the loss avoided.
            Sets the decision threshold, since the optimal one is p* = alpha.
        latitude_deg: For extraterrestrial radiation in the water balance.
            Forwarded to `pipeline.prepare_panel` -- see
            `waterbalance.run_water_balance` for the fallback-with-warning
            behaviour when it is `None` (the default).
        sowing_date: The sowing anchor. **Never inferred** -- passing None leaves
            `days_since_sowing` at None, which makes `is_dry_spell_after_sowing`
            return False, so the flagship condition simply cannot fire without a
            real anchor. That is the intended behaviour, not a limitation to work
            around: an inferred anchor makes the condition unfalsifiable, and this
            is the condition that tells a farmer to buy seed twice.

            Its month and day are applied in *every* season of the panel, not
            only in its own year. A multi-season sweep otherwise leaves the
            anchor unreachable in all seasons but one, and the condition that
            matters most goes untested. This is a stated assumption -- "sowing
            happens on this calendar date each year" -- supplied by the caller,
            not a date derived from the weather, so the distinction the docstring
            above insists on is preserved.
        onset_delay_days: Observed monsoon onset minus the local normal. Also
            never inferred -- only IMD declares onset.
        approve_for_demo: Run `simulate_reviewer_approval` first. Off by default.
            See that function's docstring before turning it on.

    Returns:
        A `DistrictRun` holding one `AdvisoryOutcome` per scored block-day,
        abstentions included.
    """
    panel = prepare_panel(observations, latitude_deg=latitude_deg)
    panel = panel.reset_index(drop=True)
    panel["rain_3d_mm"] = _rain_3d(panel)

    results = run_cross_validation(panel, lead_days=lead_days)
    if not results:
        raise ValueError("cross-validation produced no results; need more seasons")

    best = max(results, key=lambda result: result.verification.brier_skill_score)
    logger.info("serving with %s (BSS=%.3f)", best.model_name, best.verification.brier_skill_score)

    # Climatological 3-day normals, for the unseasonal-rain ratio. Fitted on the
    # same seasons the served model trained on -- every season but the last --
    # so the normal a decision is compared against never contains that decision's
    # own day.
    seasons = season_of(panel[COL_DATE])
    training_seasons = set(seasons.unique()[:-1])
    climatology = pentad_climatology(panel, training_seasons=training_seasons)
    normals = {
        (row[COL_BLOCK], int(row["pentad"])): float(row["pentad_rain_mean"]) * 3.0
        for _, row in climatology.iterrows()
    }

    candidates_by_code: dict[ConditionCode, list[DACPRule]] = {}
    for code in ConditionCode:
        found = store.candidates(state, district, code)
        if approve_for_demo:
            found = simulate_reviewer_approval(found, store)
        candidates_by_code[code] = found

    candidate_total = sum(len(rules) for rules in candidates_by_code.values())
    approved_total = sum(
        1
        for rules in candidates_by_code.values()
        for rule in rules
        if rule.review_status == ReviewStatus.APPROVED
    )

    outcomes: list[AdvisoryOutcome] = []
    probabilities = np.full(len(panel), np.nan)
    probabilities[best.scored_positions] = best.out_of_fold

    for position in best.scored_positions:
        row = panel.iloc[position]
        pentad = int((row[COL_DATE].dayofyear - 1) // 5)
        as_of = row[COL_DATE].date()

        days_since_sowing = _days_since_sowing(as_of, sowing_date)

        state = moisture_state_from_row(
            row,
            rain_3d_normal_mm=normals.get((row[COL_BLOCK], pentad), 0.0),
            days_since_sowing=days_since_sowing,
            onset_delay_days=onset_delay_days,
        )
        detected = detect_condition(state)
        probability = float(probabilities[position])

        forecast = DrySpellForecast(
            block_id=state.block_id,
            issued_on=as_of,
            lead_days=lead_days,
            probability=probability,
            climatological_rate=float(best.verification.base_rate),
            model_version=best.model_name,
        )

        rules = candidates_by_code.get(detected, []) if detected is not None else []
        page_count = store.page_count_for(rules[0]) if rules else None

        action, decision, rule, reasons = emit_advisory(
            state,
            forecast,
            rules,
            cost_loss_ratio=cost_loss_ratio,
            crop_already_sown=days_since_sowing is not None and days_since_sowing >= 0,
            document_page_count=page_count,
        )

        outcomes.append(
            AdvisoryOutcome(
                block_id=state.block_id,
                as_of=as_of,
                detected=detected,
                probability=probability,
                action=action,
                decision=decision,
                rule=rule,
                abstain_reasons=reasons,
                predicates=explain_condition(state),
            )
        )

    return DistrictRun(
        district=district,
        lead_days=lead_days,
        model_name=best.model_name,
        brier_skill_score=best.verification.brier_skill_score,
        outcomes=outcomes,
        candidate_rule_count=candidate_total,
        approved_rule_count=approved_total,
        verification=results,
    )


def format_district_report(run: DistrictRun, *, max_examples: int = 5) -> str:
    """Render a run as text, with the abstentions given equal billing.

    A report that showed only emitted advisories would describe a different
    system than the one that exists. The abstention tally and its reasons are the
    load-bearing half.
    """
    lines = [
        "=" * 96,
        f"End-to-end run -- district {run.district!r}, lead {run.lead_days}d",
        "=" * 96,
        f"served by            {run.model_name}  (BSS={run.brier_skill_score:+.3f})",
        f"candidate rules      {run.candidate_rule_count} matched by condition code",
        f"  of which approved  {run.approved_rule_count}",
        f"block-days scored    {len(run.outcomes)}",
        f"conditions detected  {len(run.detections)}",
        f"advisories emitted   {len(run.emitted)}",
        "",
    ]

    by_action = Counter(outcome.action.value for outcome in run.outcomes)
    lines.append("actions: " + ", ".join(f"{k}={v}" for k, v in sorted(by_action.items())))

    detected_counts = Counter(
        outcome.detected.value for outcome in run.detections if outcome.detected
    )
    lines.append(
        "conditions: "
        + (", ".join(f"{k}={v}" for k, v in sorted(detected_counts.items())) or "none")
    )

    reasons = Counter(
        reason
        for outcome in run.outcomes
        if not outcome.emitted
        for reason in outcome.abstain_reasons
    )
    if reasons:
        lines += ["", "why Ankur stayed silent (most common first):"]
        lines += [f"    {count:>6}  {reason}" for reason, count in reasons.most_common(8)]

    if run.emitted:
        lines += ["", f"first {min(max_examples, len(run.emitted))} advisories:"]
        for outcome in run.emitted[:max_examples]:
            rule = outcome.rule
            citation = (
                f"{rule.citation.document} p{rule.citation.page}" if rule is not None else "?"
            )
            lines += [
                f"    {outcome.as_of}  block {outcome.block_id}  "
                f"{outcome.action.value.upper()}  p={outcome.probability:.2f}",
                f"        condition: {outcome.detected.value if outcome.detected else '-'}",
                f"        cites:     {citation}",
            ]
            if rule is not None and rule.fields.action:
                lines.append(f"        action:    {rule.fields.action[:110]}")

    return "\n".join(lines)
