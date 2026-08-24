"""End-to-end orchestration: observations -> calibrated probability -> advisory.

Mirrors `document_intelligence.pipeline` in shape and intent -- each stage is
independently testable, and this module only wires them together. Nothing here
holds logic that is not also reachable by calling a stage directly.

THE ONE RULE THIS MODULE ENFORCES

Every fit happens inside the fold. The climatology, the scaler, and the model are
all refitted per fold from that fold's training seasons only. This is the easiest
place in the whole pipeline to leak, because it is so natural to compute normals
once over the record and reuse them -- and the resulting scores look plausible,
merely better than they should be. `run_cross_validation` takes
`fold.train_seasons` and threads it through every fit, so the leak cannot happen
by omission.

The load-forecasting paper's Algorithm 1 selects features at steps 23-27, before
the split at step 27. That is a leak, and it is deliberately not reproduced here.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from ankur_domain.policies import can_emit_advisory
from ankur_schemas.condition import ConditionCode, DrySpellForecast, MoistureState
from ankur_schemas.rule import DACPRule

from trigger_engine.conditions import detect_condition
from trigger_engine.config import COL_BLOCK, COL_DATE, COL_RAIN
from trigger_engine.decision import (
    PROBABILITY_DRIVEN_CONDITIONS,
    AdvisoryAction,
    Decision,
    DecisionInput,
    decide,
)
from trigger_engine.evaluation import (
    VerificationResult,
    block_bootstrap_ci,
    evaluate,
    value_curve,
)
from trigger_engine.features import build_features
from trigger_engine.labels import build_labels, drop_unlabelable, effective_sample_size
from trigger_engine.models import ClimatologyBaseline, ProbabilisticModel, default_ladder
from trigger_engine.preprocess import preprocess_observations, season_of
from trigger_engine.splits import chronological_holdout, season_folds
from trigger_engine.waterbalance import run_water_balance

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CrossValidationResult:
    """Out-of-fold predictions and scores for one model at one lead.

    `out_of_fold` holds a prediction for every scored row, each made by a model
    that never saw that row's season. It is the only prediction vector safe to fit
    a recalibration map on, and the only one safe to quote a skill score from.
    """

    model_name: str
    lead_days: int
    out_of_fold: np.ndarray
    labels: np.ndarray
    seasons: np.ndarray
    verification: VerificationResult
    bss_confidence_interval: tuple[float, float]
    fit_seconds: float
    scored_positions: np.ndarray
    """Positional indices into the panel that `out_of_fold` and `labels` describe.

    Carried so a probability can be put back beside the row it was made for. The
    serving path needs that: an advisory is issued for one block on one day, and
    the only probability it may use is the out-of-fold one, made by a model that
    never saw that row's season. Without this mapping the safe probabilities and
    the rows they belong to are two arrays nobody can join."""

    def summary_line(self) -> str:
        low, high = self.bss_confidence_interval
        return (
            f"{self.verification.summary_line()}  "
            f"BSS95%=[{low:+.3f},{high:+.3f}]  fit={self.fit_seconds:.2f}s"
        )


@dataclass(frozen=True, slots=True)
class PipelineArtifacts:
    """Everything one full run produces."""

    panel: pd.DataFrame
    features: pd.DataFrame
    results: list[CrossValidationResult] = field(default_factory=list)
    sample_size: dict[str, float] = field(default_factory=dict)


def prepare_panel(observations: pd.DataFrame, *, latitude_deg: float = 29.5) -> pd.DataFrame:
    """Preprocess, then run the water balance. The deterministic half of the pipeline.

    Separated from the modelling half because it is reusable as-is for a replay or
    a nightly job: neither needs a trained model to compute today's moisture state,
    and the DACP condition predicates run on this output alone.
    """
    panel, report = preprocess_observations(observations)
    logger.info(
        "preprocessed %d -> %d rows, %d blocks, %d seasons, %.2f%% rainfall imputed",
        report.rows_in,
        report.rows_out,
        report.blocks,
        len(report.seasons),
        100 * report.imputed_fraction,
    )
    if report.imputed_fraction > 0.10:
        # Loud, because above roughly this level the verification scores stop
        # describing the weather and start describing the gaps.
        logger.warning(
            "%.1f%% of rainfall days were unobserved; skill scores from this panel "
            "should be treated as provisional",
            100 * report.imputed_fraction,
        )
    return run_water_balance(panel, latitude_deg=latitude_deg)


def run_cross_validation(
    panel: pd.DataFrame,
    *,
    lead_days: int,
    models: list[ProbabilisticModel] | None = None,
    teleconnections: pd.DataFrame | None = None,
    n_holdout_seasons: int = 1,
) -> list[CrossValidationResult]:
    """Leave-one-season-out evaluation of every model on the ladder.

    Per fold: refit the climatology on training seasons, rebuild features using
    that climatology, fit the model, predict the held-out season. Nothing fitted on
    a test season ever touches a test-season prediction.

    Args:
        panel: Output of `prepare_panel`.
        lead_days: Forecast horizon.
        models: Defaults to `models.default_ladder()`.
        teleconnections: Optional ONI/MJO frame.
        n_holdout_seasons: Final seasons withheld from the rotation entirely.

    Returns:
        One `CrossValidationResult` per model.

    Every model is refit from scratch per fold, so cost is (folds x models) fits.
    With ~30 folds and 5 sklearn models on ~10^4 rows that is seconds in total.
    """
    models = models or default_ladder()
    seasons = season_of(panel[COL_DATE])
    holdout = chronological_holdout(seasons, n_holdout=n_holdout_seasons)
    folds = list(season_folds(seasons, holdout_seasons=holdout))
    if not folds:
        raise ValueError("no usable folds: need more seasons than min_train_seasons")

    labels_full = build_labels(panel, lead_days=lead_days)
    positions = {label: i for i, label in enumerate(panel.index)}

    predictions: dict[str, np.ndarray] = {m.name: np.full(len(panel), np.nan) for m in models}
    reference = np.full(len(panel), np.nan)
    timings: dict[str, float] = {m.name: 0.0 for m in models}

    for fold in folds:
        # Features are rebuilt per fold because the climatological anomaly inside
        # them is fitted on training seasons only. Rebuilding is the price of not
        # leaking, and it costs a fraction of a second.
        fold_features = build_features(
            panel, training_seasons=set(fold.train_seasons), teleconnections=teleconnections
        )
        train_x, train_y = drop_unlabelable(
            fold_features.iloc[fold.train_index], labels_full.iloc[fold.train_index]
        )
        test_x, _ = drop_unlabelable(
            fold_features.iloc[fold.test_index], labels_full.iloc[fold.test_index]
        )
        if len(train_x) == 0 or len(test_x) == 0:
            continue

        test_positions = np.array([positions[i] for i in test_x.index])

        # The reference forecast, fitted per fold like everything else.
        climatology = ClimatologyBaseline().fit(train_x, train_y)
        reference[test_positions] = climatology.predict_proba(test_x)

        for model in models:
            started = time.perf_counter()
            model.fit(train_x, train_y)
            predictions[model.name][test_positions] = model.predict_proba(test_x)
            timings[model.name] += time.perf_counter() - started

    label_values = labels_full.to_numpy(dtype=float)
    season_values = seasons.to_numpy()

    results: list[CrossValidationResult] = []
    for model in models:
        scored = ~np.isnan(predictions[model.name]) & ~np.isnan(label_values) & ~np.isnan(reference)
        if not scored.any():
            continue

        y, p = label_values[scored], predictions[model.name][scored]
        ref, grp = reference[scored], season_values[scored]

        results.append(
            CrossValidationResult(
                model_name=model.name,
                lead_days=lead_days,
                out_of_fold=p,
                labels=y,
                seasons=grp,
                verification=evaluate(model.name, lead_days, y, p, ref),
                bss_confidence_interval=block_bootstrap_ci(
                    y, p, grp, statistic="bss", reference=ref, n_resamples=300
                ),
                fit_seconds=timings[model.name],
                scored_positions=np.flatnonzero(scored),
            )
        )
    return results


def moisture_state_from_row(
    row: pd.Series,
    *,
    rain_3d_normal_mm: float,
    days_since_sowing: int | None = None,
    onset_delay_days: int | None = None,
) -> MoistureState:
    """Project one panel row into the schema the condition predicates consume.

    A narrow, explicit adapter rather than passing a DataFrame row around. It
    forces `days_since_sowing` and `onset_delay_days` to be supplied by the caller,
    which is the mechanical expression of "never infer the sowing anchor": there is
    no code path that fills them in from the weather.
    """
    rain_3d = row.get("rain_3d_mm")
    if rain_3d is None or pd.isna(rain_3d):
        rain_3d = row[COL_RAIN]
    return MoistureState(
        block_id=str(row[COL_BLOCK]),
        as_of=row[COL_DATE].date(),
        soil_moisture_fraction=float(row["soil_moisture_fraction"]),
        consecutive_dry_days=int(row["consecutive_dry_days"]),
        days_since_sowing=days_since_sowing,
        onset_delay_days=onset_delay_days,
        rain_3d_mm=float(0.0 if pd.isna(rain_3d) else rain_3d),
        rain_3d_normal_mm=rain_3d_normal_mm,
    )


def emit_advisory(
    state: MoistureState,
    forecast: DrySpellForecast,
    candidate_rules: list[DACPRule],
    *,
    cost_loss_ratio: float,
    crop_already_sown: bool = False,
    document_page_count: int | None = None,
) -> tuple[AdvisoryAction, Decision | None, DACPRule | None, list[str]]:
    """The final gate. Returns ABSTAIN unless every requirement is met.

    Order is deliberate, and each step can only ever *reduce* what gets said:

      1. detect the condition from observed physics;
      2. find an approved rule whose `condition_code` matches it;
      3. ask `ankur_domain.policies.can_emit_advisory` whether emission is allowed;
      4. only then convert the probability into an action.

    The probability never enters steps 1-3. A high probability cannot conjure a
    rule, and a matched rule cannot fire without one -- which is what keeps this
    system retrieving government advice rather than generating advice of its own.

    Returns:
        `(action, decision, rule, abstain_reasons)`. On ABSTAIN, `decision` and
        `rule` are None and `abstain_reasons` explains why -- an audit record needs
        the reason as much as the outcome.
    """
    detected: ConditionCode | None = detect_condition(state)

    matched = next(
        (rule for rule in candidate_rules if rule.fields.condition_code == detected),
        None,
    )

    may_emit, reasons = can_emit_advisory(matched, detected, page_count=document_page_count)
    if not may_emit:
        return AdvisoryAction.ABSTAIN, None, None, reasons

    # Step 3b: the decision layer only speaks about dry spells. A condition it
    # does not model must not borrow its thresholds -- see
    # `decision.PROBABILITY_DRIVEN_CONDITIONS` for the flood row that made this
    # necessary. Passing `can_emit_advisory` means the plan has something to say
    # here; it does not mean `decide` knows how to say it.
    if detected not in PROBABILITY_DRIVEN_CONDITIONS:
        return (
            AdvisoryAction.ABSTAIN,
            None,
            None,
            [
                f"condition {detected.value!r} has an approved cited rule, but no "
                f"probabilistic decision rule covers it yet"
            ],
        )

    decision = decide(
        DecisionInput(
            probability=forecast.probability,
            cost_loss_ratio=cost_loss_ratio,
            crop_already_sown=crop_already_sown,
            days_since_sowing=state.days_since_sowing,
        )
    )
    return decision.action, decision, matched, []


def run_demo(*, seasons: range = range(1995, 2026), lead_days: int = 14) -> PipelineArtifacts:
    """Smoke run over synthetic data. Exercises every stage; proves nothing about skill.

    Deliberately loud about what it is. The numbers it prints say the code is wired
    correctly and runs fast; they say nothing about whether the method works,
    because the weather comes from `synthetic.py`. Real verification needs IMD
    gridded rainfall and ECMWF reforecasts -- see `docs/ml-pipeline.md`.
    """
    from trigger_engine.synthetic import generate_panel, generate_teleconnections

    started = time.perf_counter()
    observations = generate_panel(seasons=seasons)
    teleconnections = generate_teleconnections(seasons=seasons)

    panel = prepare_panel(observations)
    results = run_cross_validation(panel, lead_days=lead_days, teleconnections=teleconnections)

    labels = build_labels(panel, lead_days=lead_days)
    all_seasons = season_of(panel[COL_DATE])
    sample_size = effective_sample_size(
        labels, all_seasons, lead_days=lead_days, blocks=panel[COL_BLOCK]
    )
    features = build_features(panel, training_seasons=set(all_seasons.unique()))

    logger.info("demo run complete in %.2fs", time.perf_counter() - started)
    return PipelineArtifacts(
        panel=panel, features=features, results=results, sample_size=sample_size
    )


def format_report(artifacts: PipelineArtifacts) -> str:
    """Render a run as text, with the caveats attached to the numbers.

    Metrics that need context are never printed bare: the base rate sits beside
    every Brier score and the bootstrap interval beside every BSS, so a reader
    cannot take a headline number without also seeing what it is relative to.
    """
    lines = [
        "=" * 104,
        "Ankur trigger engine -- leave-one-season-out verification",
        "SYNTHETIC DATA: these numbers verify the code, not the method.",
        "=" * 104,
        "",
        f"effective sample size: {artifacts.sample_size}",
        "",
    ]
    ranked = sorted(artifacts.results, key=lambda r: -r.verification.brier_skill_score)
    lines += ["  " + result.summary_line() for result in ranked]

    if ranked:
        best = ranked[0]
        lines += ["", f"economic value curve (alpha, V) for {best.model_name}:"]
        curve = value_curve(best.labels, best.out_of_fold, n_points=7)
        lines.append("  " + "  ".join(f"({a:.2f},{v:+.2f})" for a, v in curve))

    return "\n".join(lines)
