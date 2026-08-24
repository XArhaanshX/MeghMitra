"""Unit tests for the trigger engine.

Several of these are not ordinary tests -- they are the product's safety claims
written as CI, in the same spirit as `tests/unit/test_citations.py`:

    test_features_are_causal                    no feature reads the present
    test_climatology_is_fitted_in_fold          no fit sees a test season
    test_every_condition_code_has_a_predicate   the vocabulary is total
    test_abstain_is_the_default                 silence unless every gate passes

The first two catch leakage, the failure mode that produces excellent validation
scores and worthless forecasts. The last two catch the failure mode that produces
confident agricultural advice with nothing behind it.

No network, no Postgres, no PDF -- all weather comes from `synthetic`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from ankur_domain.policies import can_emit_advisory, has_valid_citation
from ankur_schemas.citation import Citation
from ankur_schemas.condition import ConditionCode, MoistureState
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRule, DACPRuleFields
from trigger_engine import conditions, evaluation, labels, models, preprocess, waterbalance
from trigger_engine.config import COL_BLOCK, COL_DATE, COL_RAIN, RAINY_DAY_THRESHOLD_MM
from trigger_engine.decision import (
    AdvisoryAction,
    Decision,
    DecisionInput,
    apply_hysteresis,
    decide,
    optimal_threshold,
    seed_demand_quintals,
)
from trigger_engine.features import FEATURE_SPECS, build_features, pentad_climatology
from trigger_engine.splits import season_folds
from trigger_engine.synthetic import generate_panel


@pytest.fixture(scope="module")
def small_panel() -> pd.DataFrame:
    """Six seasons, two blocks. Small enough to be fast, long enough to fold."""
    observations = generate_panel(
        seasons=range(2015, 2021), blocks=("Sirsa", "Ellenabad"), missing_rain_fraction=0.02
    )
    panel, _ = preprocess.preprocess_observations(observations)
    return waterbalance.run_water_balance(panel)


def _observations(rain: list[float]) -> pd.DataFrame:
    """Minimal single-block observation frame of the given rainfall series."""
    return pd.DataFrame(
        {
            COL_BLOCK: ["A"] * len(rain),
            COL_DATE: pd.date_range("2020-07-01", periods=len(rain)),
            COL_RAIN: rain,
            "tmin_c": [25.0] * len(rain),
            "tmax_c": [35.0] * len(rain),
        }
    )


# ---------------------------------------------------------------------------
# Preprocessing -- the three rules inverted from the load-forecasting template
# ---------------------------------------------------------------------------


def test_rainfall_is_never_forward_filled() -> None:
    """A missing rain day must stay missing, and be flagged.

    Forward-filling would carry yesterday's rain into today and invent an event;
    zero-filling would invent a dry day and bias the dry-spell target. Both are
    silent, and both make the model look better than it is.
    """
    panel, report = preprocess.preprocess_observations(
        _observations([40.0, np.nan, 0.0, 0.0, 5.0]), include_spinup=False
    )
    gap = panel.loc[panel[COL_DATE] == pd.Timestamp("2020-07-02")].iloc[0]

    assert pd.isna(gap[COL_RAIN]), "missing rainfall was imputed; it must stay NaN"
    assert bool(gap["rain_is_imputed"]) is True
    assert report.missing_rain_days == 1


def test_extreme_rainfall_survives_but_impossible_rainfall_does_not() -> None:
    """Physical cap, not 4-sigma winsorization.

    A 250 mm burst is a real monsoon event and the signal we exist to detect -- it
    must pass through untouched even though it is far beyond mu + 4 sigma of this
    sample. A 5000 mm reading is an instrument error and must be voided.
    """
    panel, report = preprocess.preprocess_observations(
        _observations([0.0, 250.0, 5000.0, -3.0]), include_spinup=False
    )
    values = panel.sort_values(COL_DATE)[COL_RAIN].to_numpy()

    assert values[1] == 250.0, "a genuine monsoon burst was clipped away"
    assert np.isnan(values[2]), "an impossible value was kept"
    assert np.isnan(values[3]), "negative rainfall was kept or clamped instead of voided"
    assert report.implausible_rain_values == 2


def test_missing_days_become_rows() -> None:
    """A calendar gap must become NaN rows, not vanish.

    If gaps stay absent, a rolling 7-day window silently spans 9 calendar days and
    every lag is wrong by a varying amount -- an error that never raises.
    """
    observations = pd.DataFrame(
        {
            COL_BLOCK: ["A", "A"],
            COL_DATE: [pd.Timestamp("2020-07-01"), pd.Timestamp("2020-07-05")],
            COL_RAIN: [1.0, 2.0],
            "tmin_c": [25.0, 25.0],
            "tmax_c": [35.0, 35.0],
        }
    )
    panel, _ = preprocess.preprocess_observations(observations, include_spinup=False)
    assert len(panel) == 5, "the 3-day gap was not materialised as rows"


# ---------------------------------------------------------------------------
# Causality -- the leakage guards
# ---------------------------------------------------------------------------


def test_features_are_causal(small_panel: pd.DataFrame) -> None:
    """No feature value on day t changes when all data from t onward is deleted.

    The strongest available check for leakage, and the reason `FeatureSpec`
    declares `min_shift_days`: rebuild the matrix from a truncated panel and
    require the surviving rows to match.

    `ens_dry_fraction` is excluded because it legitimately carries shift 0 -- a
    forecast issued on day t is available on day t. Everything with a positive
    declared shift must match exactly.
    """
    cutoff = pd.Timestamp("2018-08-01")
    seasons = {2015, 2016, 2017}

    full = build_features(small_panel, training_seasons=seasons)
    truncated = build_features(
        small_panel.loc[small_panel[COL_DATE] < cutoff], training_seasons=seasons
    )

    shared = truncated.index.intersection(full.index)
    assert len(shared) > 100, "truncation left too few rows to be a meaningful check"

    for spec in (s for s in FEATURE_SPECS if s.min_shift_days > 0):
        a = full.loc[shared, spec.name].to_numpy(dtype=float)
        b = truncated.loc[shared, spec.name].to_numpy(dtype=float)
        both = ~np.isnan(a) & ~np.isnan(b)
        assert np.allclose(a[both], b[both]), (
            f"feature {spec.name!r} changed when future data was removed -- it leaks"
        )


def test_labels_may_see_the_future_but_are_never_fabricated(small_panel: pd.DataFrame) -> None:
    """A label that cannot be known must be NaN, not an invented negative."""
    y = labels.build_labels(small_panel, lead_days=14)
    last_rows = y.groupby(small_panel[COL_BLOCK]).tail(3)
    assert last_rows.isna().all(), "labels were fabricated at the end of the record"


def test_climatology_is_fitted_in_fold(small_panel: pd.DataFrame) -> None:
    """Normals computed on different training sets must actually differ.

    Climatological normals feel like a fixed property of a place, which is exactly
    why it is tempting to compute them once over the whole record. Doing so puts
    test-season rainfall into a feature used to predict the test season. If these
    two are identical, `training_seasons` is being ignored.
    """
    early = pentad_climatology(small_panel, training_seasons={2015, 2016})
    late = pentad_climatology(small_panel, training_seasons={2018, 2019})
    merged = early.merge(late, on=[COL_BLOCK, "pentad"], suffixes=("_early", "_late"))

    assert not np.allclose(
        merged["pentad_rain_mean_early"].fillna(0), merged["pentad_rain_mean_late"].fillna(0)
    ), "climatology ignored training_seasons -- it is fitted on the whole record"


def test_folds_never_share_a_season(small_panel: pd.DataFrame) -> None:
    """A season on both sides of a fold makes the score meaningless."""
    seasons = preprocess.season_of(small_panel[COL_DATE])
    folds = list(season_folds(seasons))
    assert folds, "no folds produced"

    for fold in folds:
        assert fold.test_season not in fold.train_seasons
        assert fold.test_season not in set(seasons.to_numpy()[fold.train_index])


# ---------------------------------------------------------------------------
# Water balance
# ---------------------------------------------------------------------------


def test_soil_moisture_stays_within_the_bucket(small_panel: pd.DataFrame) -> None:
    """Clipping at 0 and AWC is what makes this a bucket, not a reservoir."""
    fraction = small_panel["soil_moisture_fraction"].dropna()
    assert fraction.min() >= 0.0
    assert fraction.max() <= 1.0


def test_et0_responds_to_diurnal_range() -> None:
    """Hargreaves reads diurnal range as a cloudiness proxy.

    A wide range means clear skies and high evaporative demand; a narrow one means
    overcast. If ET0 did not rise with the range, the equation is misapplied.
    """
    doy = np.array([200])
    clear = waterbalance.reference_et0(np.array([22.0]), np.array([40.0]), 29.5, doy)
    overcast = waterbalance.reference_et0(np.array([26.0]), np.array([30.0]), 29.5, doy)
    assert clear[0] > overcast[0]


def test_dry_run_resets_on_rain() -> None:
    """The vectorized reset-on-wet counter must match the obvious loop."""
    frame = pd.DataFrame({COL_BLOCK: ["A"] * 7, COL_RAIN: [0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0]})
    assert waterbalance.consecutive_dry_days(frame).tolist() == [1, 2, 3, 0, 1, 2, 3]


def test_unobserved_day_does_not_extend_a_dry_spell() -> None:
    """A data gap must not manufacture a drought."""
    frame = pd.DataFrame({COL_BLOCK: ["A"] * 4, COL_RAIN: [0.0, np.nan, 0.0, 0.0]})
    assert waterbalance.consecutive_dry_days(frame).tolist()[1] == 0


# ---------------------------------------------------------------------------
# Conditions -- the vocabulary contract
# ---------------------------------------------------------------------------


def test_every_condition_code_has_a_predicate() -> None:
    """The rule base must not advertise coverage the engine cannot detect.

    Adding a `ConditionCode` without a predicate would let an extracted rule carry
    a code that can never match, and the gap would surface only as an advisory
    that silently never fires.
    """
    emittable = {code for code in ConditionCode if code is not ConditionCode.UNMAPPED}
    assert set(conditions.CONDITION_PREDICATES) == emittable
    assert set(conditions.CONDITION_PRIORITY) == emittable


def _state(**overrides: object) -> MoistureState:
    """A neutral, non-triggering state; override one field per test."""
    defaults = {
        "block_id": "Sirsa",
        "as_of": date(2020, 7, 15),
        "soil_moisture_fraction": 0.8,
        "consecutive_dry_days": 0,
        "days_since_sowing": None,
        "onset_delay_days": None,
        "rain_3d_mm": 10.0,
        "rain_3d_normal_mm": 10.0,
    }
    return MoistureState(**(defaults | overrides))


def test_ordinary_weather_detects_nothing() -> None:
    """Most monsoon days are unremarkable, and None is the correct answer."""
    assert conditions.detect_condition(_state()) is None


def test_dry_spell_over_wet_soil_does_not_fire() -> None:
    """The meteorological/agricultural distinction, which is the whole point.

    A dry spell over a wet profile means the crop is fine. Firing a re-sow
    advisory would cost a farmer a seed bag for nothing.
    """
    state = _state(consecutive_dry_days=10, soil_moisture_fraction=0.9, days_since_sowing=10)
    assert conditions.detect_condition(state) is None


def test_dry_spell_after_sowing_fires_on_dry_soil() -> None:
    state = _state(consecutive_dry_days=10, soil_moisture_fraction=0.2, days_since_sowing=10)
    assert conditions.detect_condition(state) is ConditionCode.DRY_SPELL_AFTER_SOWING


def test_sowing_anchor_is_never_inferred() -> None:
    """Without an anchor the after-sowing condition cannot fire, whatever the weather.

    An inferred sowing date would make the flagship condition unfalsifiable, and it
    is the condition that tells a farmer to spend money on seed twice.
    """
    state = _state(consecutive_dry_days=20, soil_moisture_fraction=0.1, days_since_sowing=None)
    assert conditions.detect_condition(state) is not ConditionCode.DRY_SPELL_AFTER_SOWING


def test_specific_condition_wins_over_general() -> None:
    """After-sowing outranks mid-season: it carries the re-sow variety."""
    state = _state(consecutive_dry_days=10, soil_moisture_fraction=0.1, days_since_sowing=5)
    assert conditions.detect_condition(state) is ConditionCode.DRY_SPELL_AFTER_SOWING


def test_unseasonal_rain_needs_a_nonzero_normal() -> None:
    """Dividing by a zero normal would make any rain infinitely unseasonal."""
    state = _state(rain_3d_mm=50.0, rain_3d_normal_mm=0.0)
    assert conditions.detect_condition(state) is not ConditionCode.UNSEASONAL_RAIN


# ---------------------------------------------------------------------------
# The ABSTAIN invariant
# ---------------------------------------------------------------------------


def _rule(
    *,
    status: ReviewStatus = ReviewStatus.APPROVED,
    code: ConditionCode | None = ConditionCode.DRY_SPELL_AFTER_SOWING,
    page: int = 37,
) -> DACPRule:
    return DACPRule(
        id=uuid4(),
        fields=DACPRuleFields(
            district="Sirsa",
            condition="Normal onset followed by 15-20 day dry spell after sowing",
            condition_code=code,
            crop="Pearl millet",
            action="Re-sow",
            variety="HHB-67 Improved",
        ),
        citation=Citation(document="HAR16-Sirsa-30-06-2011.pdf", page=page),
        confidence=0.94,
        extractor_version="test",
        extracted_at=datetime.now(UTC),
        review_status=status,
    )


def test_abstain_is_the_default() -> None:
    """No condition and no rule means silence, with a reason recorded."""
    may_emit, reasons = can_emit_advisory(None, None)
    assert may_emit is False
    assert reasons


def test_unapproved_rule_cannot_fire() -> None:
    """Confidence gates the review queue; only approval gates emission.

    The committed fixture shows why these are different axes: one rule sits at
    confidence 0.88 and is still `pending`.
    """
    for status in (ReviewStatus.PENDING, ReviewStatus.NEEDS_REVIEW, ReviewStatus.REJECTED):
        may_emit, reasons = can_emit_advisory(
            _rule(status=status), ConditionCode.DRY_SPELL_AFTER_SOWING
        )
        assert may_emit is False, f"a {status.value} rule was allowed to fire"
        assert any("review_status" in r for r in reasons)


def test_mismatched_condition_code_cannot_fire() -> None:
    """Guards a caller that fetched a rule on another axis and assumed a match."""
    may_emit, reasons = can_emit_advisory(
        _rule(code=ConditionCode.UNSEASONAL_RAIN), ConditionCode.DRY_SPELL_AFTER_SOWING
    )
    assert may_emit is False
    assert any("does not match" in r for r in reasons)


def test_unmapped_condition_is_not_emittable() -> None:
    """A normalization failure must not become agricultural advice."""
    may_emit, _ = can_emit_advisory(_rule(code=ConditionCode.UNMAPPED), ConditionCode.UNMAPPED)
    assert may_emit is False


def test_approved_rule_with_matching_code_may_fire() -> None:
    """The positive case -- otherwise the tests above would pass trivially."""
    may_emit, reasons = can_emit_advisory(_rule(), ConditionCode.DRY_SPELL_AFTER_SOWING)
    assert may_emit is True, f"a valid advisory was blocked: {reasons}"
    assert reasons == []


def test_citation_beyond_the_document_is_rejected_when_page_count_is_known() -> None:
    """The gap that let the committed fixture cite page 37 of a 31-page PDF.

    Without a page bound, `page >= 1` accepts any number. The ingestion pipeline
    was already safe; the policy was not, so any other path that builds a rule
    bypassed the check entirely.
    """
    citation = Citation(document="HAR16-Sirsa-30-06-2011.pdf", page=37)
    assert has_valid_citation(citation) is True, "default behaviour must be unchanged"
    assert has_valid_citation(citation, page_count=31) is False

    may_emit, reasons = can_emit_advisory(
        _rule(page=37), ConditionCode.DRY_SPELL_AFTER_SOWING, page_count=31
    )
    assert may_emit is False
    assert any("citation" in r for r in reasons)


# ---------------------------------------------------------------------------
# Decision layer
# ---------------------------------------------------------------------------


def test_threshold_equals_cost_loss_ratio() -> None:
    """p* = alpha, the standard cost-loss result. Not a tuned cutoff."""
    assert optimal_threshold(0.35) == pytest.approx(0.35)
    with pytest.raises(ValueError):
        optimal_threshold(0.0)


def test_low_cost_farmer_is_warned_earlier() -> None:
    """The same probability yields different correct answers for different farmers.

    A smallholder for whom a failed season is ruinous (small alpha) should be
    warned at a probability where an irrigated farm (large alpha) should not.
    """
    cautious = decide(DecisionInput(probability=0.30, cost_loss_ratio=0.15))
    tolerant = decide(DecisionInput(probability=0.30, cost_loss_ratio=0.60))
    assert cautious.action is AdvisoryAction.WAIT
    assert tolerant.action is AdvisoryAction.SOW


def test_sown_crop_gets_resow_not_wait() -> None:
    """Waiting is meaningless once the crop is committed."""
    decision = decide(
        DecisionInput(
            probability=0.9, cost_loss_ratio=0.3, crop_already_sown=True, days_since_sowing=12
        )
    )
    assert decision.action is AdvisoryAction.RE_SOW


def _decision(action: AdvisoryAction) -> Decision:
    return Decision(action=action, probability=0.5, threshold=0.5, reason="test")


def test_hysteresis_suppresses_a_single_flip() -> None:
    """One oscillating day must not flip the advisory.

    Without this, a probability jittering around alpha produces WAIT, SOW, WAIT on
    consecutive days -- individually defensible, collectively worthless, and given
    the SMS commitment, expensive.
    """
    sequence = [
        _decision(AdvisoryAction.WAIT),
        _decision(AdvisoryAction.SOW),
        _decision(AdvisoryAction.WAIT),
    ]
    assert [s.action for s in apply_hysteresis(sequence, cycles=2)] == [AdvisoryAction.WAIT] * 3


def test_hysteresis_allows_a_sustained_change() -> None:
    """It must delay a change, not prevent one."""
    sequence = [_decision(AdvisoryAction.WAIT)] + [_decision(AdvisoryAction.SOW)] * 3
    assert apply_hysteresis(sequence, cycles=2)[-1].action is AdvisoryAction.SOW


def test_missing_seed_rate_is_not_treated_as_zero() -> None:
    """`seed_rate` is null in every rule of the current Sirsa fixture.

    A missing rate must raise rather than silently produce a zero-quintal
    recommendation, which a BAO could read as "stage nothing".
    """
    with pytest.raises(ValueError):
        seed_demand_quintals(hectares=100.0, trigger_probability=0.5, seed_rate_kg_per_ha=0.0)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def test_brier_skill_score_is_zero_against_itself() -> None:
    """A forecast scored against itself has no skill, by definition."""
    y = np.array([0.0, 1.0, 1.0, 0.0])
    p = np.array([0.3, 0.7, 0.6, 0.2])
    assert evaluation.brier_skill_score(y, p, p) == pytest.approx(0.0)


def test_murphy_decomposition_reconstructs_the_brier_score() -> None:
    """BS = reliability - resolution + uncertainty. If not, a term is wrong."""
    rng = np.random.default_rng(0)
    y = (rng.random(500) < 0.3).astype(float)
    p = np.clip(y * 0.4 + rng.random(500) * 0.5, 0.01, 0.99)

    reliability, resolution, uncertainty = evaluation.murphy_decomposition(y, p, n_bins=10)
    assert evaluation.brier_score(y, p) == pytest.approx(
        reliability - resolution + uncertainty, abs=1e-3
    )


def test_perfectly_calibrated_forecast_has_low_ece() -> None:
    rng = np.random.default_rng(1)
    p = rng.random(20000)
    y = (rng.random(20000) < p).astype(float)
    assert evaluation.expected_calibration_error(y, p) < 0.02


def test_block_bootstrap_is_wider_than_naive_resampling() -> None:
    """Resampling rows instead of seasons produces an interval that is too narrow.

    This is the statistical form of quoting "34,000 block-days" as the sample size.
    The test pins the direction of that error.
    """
    rng = np.random.default_rng(2)
    seasons = np.repeat(np.arange(10), 200)
    # Season-level shocks: rows within a season are correlated, as in real weather.
    season_rate = rng.random(10) * 0.6 + 0.2
    y = (rng.random(2000) < season_rate[seasons]).astype(float)
    # The forecast must vary, otherwise the Brier score is constant: at p = 0.5,
    # (0.5 - 0)^2 and (0.5 - 1)^2 are both 0.25, so no resampling scheme could
    # move it and the comparison would be vacuous.
    p = np.clip(season_rate[seasons] + rng.normal(0, 0.05, 2000), 0.01, 0.99)

    by_season = evaluation.block_bootstrap_ci(y, p, seasons, n_resamples=300)
    by_row = evaluation.block_bootstrap_ci(y, p, np.arange(2000), n_resamples=300)

    assert (by_season[1] - by_season[0]) > (by_row[1] - by_row[0])


def test_economic_value_is_zero_for_a_climatology_forecast() -> None:
    """A constant forecast captures none of the available value, at any alpha.

    Checked on both sides of the base rate, because the two cases exercise
    different branches: below the base rate the user acts every day, above it they
    never act, and a climatology forecast must score V = 0 either way.

    alpha is kept away from the base rate deliberately. At alpha exactly equal to
    it, `p > alpha` sits on a knife edge and the result is an artifact of the
    strict inequality rather than a property of the forecast.
    """
    rng = np.random.default_rng(3)
    y = (rng.random(4000) < 0.3).astype(float)
    climatological = np.full(4000, float(y.mean()))

    for alpha in (0.15, 0.60):
        value = evaluation.economic_value(y, climatological, cost_loss_ratio=alpha)
        assert value == pytest.approx(0.0, abs=1e-9), f"non-zero value at alpha={alpha}"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def test_monotonic_constraints_are_respected(small_panel: pd.DataFrame) -> None:
    """More ensemble members forecasting dryness must never lower the probability.

    Physics, not a tuning preference, and it is what makes a boosted model
    defensible to an agronomist at this sample size.
    """
    seasons = set(preprocess.season_of(small_panel[COL_DATE]).unique())
    features = build_features(small_panel, training_seasons=seasons)
    x, y = labels.drop_unlabelable(features, labels.build_labels(small_panel, lead_days=14))

    model = models.GradientBoostedCalibrator().fit(x, y)
    probe = x.iloc[:200]
    low = model.predict_proba(probe.assign(ens_dry_fraction=0.1))
    high = model.predict_proba(probe.assign(ens_dry_fraction=0.9))

    assert (high >= low - 1e-9).all(), "monotonic constraint on ens_dry_fraction was violated"


def test_extended_logistic_is_coherent_across_spell_lengths(small_panel: pd.DataFrame) -> None:
    """P(spell >= 15d) must not exceed P(spell >= 5d).

    Every 15-day spell contains a 5-day one, so the reverse is impossible. This
    coherence is the reason for the extended form rather than one model per length.
    """
    seasons = set(preprocess.season_of(small_panel[COL_DATE]).unique())
    features = build_features(small_panel, training_seasons=seasons)

    per_threshold = {
        g: labels.build_labels(small_panel, lead_days=14, min_days=g) for g in (5, 10, 15)
    }
    usable = features.notna().all(axis=1)
    for series in per_threshold.values():
        usable &= series.notna()

    aligned_x = features.loc[usable]
    aligned_y = {g: s.loc[usable].to_numpy(dtype=float) for g, s in per_threshold.items()}

    model = models.ExtendedLogisticRegression().fit_extended(aligned_x, aligned_y)
    p5 = model.predict_proba_at(aligned_x, 5)
    p15 = model.predict_proba_at(aligned_x, 15)

    assert (p15 <= p5 + 1e-9).all(), "longer spells were predicted as more likely"
    assert model.coherence_violation is False


def test_probabilities_never_reach_certainty(small_panel: pd.DataFrame) -> None:
    """No weather model may say "certainly not"."""
    seasons = set(preprocess.season_of(small_panel[COL_DATE]).unique())
    features = build_features(small_panel, training_seasons=seasons)
    x, y = labels.drop_unlabelable(features, labels.build_labels(small_panel, lead_days=14))

    for model in models.default_ladder():
        p = model.fit(x, y).predict_proba(x)
        assert p.min() > 0.0 and p.max() < 1.0, f"{model.name} emitted a certainty"


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def test_dry_spell_start_requires_a_full_run() -> None:
    """Four dry days do not make a five-day spell."""
    frame = pd.DataFrame(
        {
            COL_BLOCK: ["A"] * 10,
            COL_RAIN: [10.0, 0.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 0.0],
            "rain_is_imputed": [False] * 10,
        }
    )
    assert not bool(labels.dry_spell_starts(frame, min_days=5).iloc[1])


def test_dry_spell_start_is_not_a_continuation() -> None:
    """Only the first day of a run counts, or one spell would label many rows."""
    frame = pd.DataFrame(
        {
            COL_BLOCK: ["A"] * 8,
            COL_RAIN: [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "rain_is_imputed": [False] * 8,
        }
    )
    starts = labels.dry_spell_starts(frame, min_days=5)
    assert bool(starts.iloc[1]) is True
    assert bool(starts.iloc[2]) is False


def test_effective_sample_size_is_far_below_the_row_count(small_panel: pd.DataFrame) -> None:
    """The whole purpose of this function is to refuse to flatter the sample.

    Row count overstates independent information by roughly (lead_days x blocks),
    and reporting the raw count would make every confidence interval far too
    narrow.
    """
    stats = labels.effective_sample_size(
        labels.build_labels(small_panel, lead_days=14),
        preprocess.season_of(small_panel[COL_DATE]),
        lead_days=14,
        blocks=small_panel[COL_BLOCK],
    )
    assert stats["approx_independent_events"] < stats["rows"] / 20


def test_rainy_day_threshold_matches_imd() -> None:
    """2.5 mm is IMD's definition, not ours. Changing it changes the product."""
    assert RAINY_DAY_THRESHOLD_MM == 2.5
