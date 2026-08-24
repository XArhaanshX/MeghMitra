"""Verification for probability forecasts.

MAE, RMSE and MAPE -- the load-forecasting benchmark's whole metric set -- do not
apply here and are deliberately absent. Those measure the distance between a
predicted number and an observed number. This system predicts a *probability* of
a binary event, and the observation is 0 or 1; "MAPE of a probability" is not a
quantity. Using the wrong metric family is the commonest way a forecasting
project fools itself.

What is measured instead, and why each is needed:

  Brier score        Mean squared error of the probability. A proper scoring
                     rule: minimised by reporting your true belief, so it cannot
                     be gamed by hedging toward the base rate.
  Brier skill score  BS relative to climatology. The headline. BSS <= 0 means the
                     forecast adds nothing to knowing the calendar.
  Reliability        Do events happen 30% of the time when we say 30%? A model
                     can discriminate perfectly and still be badly calibrated,
                     and calibration is what a cost-loss decision rule needs.
  ECE                Reliability compressed to one number, for tracking drift.
  Sharpness          How far from the base rate the forecasts dare to go. A
                     perfectly reliable model that always says "climatology" is
                     useless; reliability without sharpness is vacuous.
  ROC-AUC            Pure discrimination, independent of calibration. Separates
                     "ranks days correctly but mis-scales" from "cannot tell days
                     apart".
  Economic value     What the forecast is worth to a decision-maker at a given
                     cost-loss ratio. The only metric a farmer would recognise.

Every function takes `(labels, probabilities)` as plain numpy arrays, so anything
on the model ladder is scored the same way.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.metrics import roc_auc_score

from trigger_engine.config import RANDOM_SEED


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    """One bin of a reliability diagram."""

    lower: float
    upper: float
    count: int
    mean_forecast: float
    observed_frequency: float


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Everything measured for one model at one lead.

    `base_rate` and `n` sit alongside the scores on purpose. A Brier score of
    0.05 looks excellent until you learn the base rate is 0.05, at which point a
    constant forecast achieves the same. Reporting the score without the base
    rate is how projects mislead themselves and their reviewers.
    """

    model_name: str
    lead_days: int
    n: int
    base_rate: float
    brier_score: float
    brier_skill_score: float
    reliability_error: float
    resolution: float
    expected_calibration_error: float
    sharpness: float
    roc_auc: float
    bins: tuple[ReliabilityBin, ...] = field(default=())

    def summary_line(self) -> str:
        """One-line rendering for the results table."""
        return (
            f"{self.model_name:<28} L={self.lead_days:>2}d  "
            f"BS={self.brier_score:.4f}  BSS={self.brier_skill_score:+.3f}  "
            f"ECE={self.expected_calibration_error:.4f}  "
            f"AUC={self.roc_auc:.3f}  sharp={self.sharpness:.4f}  "
            f"n={self.n}  base={self.base_rate:.3f}"
        )


def brier_score(labels: np.ndarray, probabilities: np.ndarray) -> float:
    """Mean squared error between forecast probability and binary outcome.

        BS = (1/n) * sum (p_i - o_i)^2

    Lower is better; 0 is perfect. Proper, so honest reporting is optimal.
    """
    return float(np.mean((probabilities - labels) ** 2))


def brier_skill_score(
    labels: np.ndarray, probabilities: np.ndarray, reference: np.ndarray
) -> float:
    """Brier score relative to a reference forecast, usually climatology.

        BSS = 1 - BS_forecast / BS_reference

    1 is perfect, 0 is no better than the reference, negative is worse. The
    headline metric, because it answers the only question that matters for a
    system positioned as adding value on top of IMD: does it beat simply knowing
    what usually happens?

    Returns NaN when the reference is itself perfect (BS_ref = 0), which happens
    only in a degenerate season with no variation; dividing by it would produce a
    meaningless infinity.
    """
    reference_bs = brier_score(labels, reference)
    if reference_bs <= 0:
        return float("nan")
    return float(1.0 - brier_score(labels, probabilities) / reference_bs)


def reliability_bins(
    labels: np.ndarray, probabilities: np.ndarray, n_bins: int = 10
) -> list[ReliabilityBin]:
    """Group forecasts by predicted probability and measure what actually happened.

    The reliability diagram plots `observed_frequency` against `mean_forecast`; a
    perfectly calibrated model lies on the diagonal. Empty bins are skipped rather
    than reported as zero, which would draw a misleading point at the diagram's
    origin.
    """
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # Clamping keeps p == 1.0 in the last bin rather than overflowing into a
    # non-existent bin index.
    indices = np.clip(np.digitize(probabilities, edges[1:-1], right=False), 0, n_bins - 1)

    bins: list[ReliabilityBin] = []
    for b in range(n_bins):
        mask = indices == b
        count = int(mask.sum())
        if count == 0:
            continue
        bins.append(
            ReliabilityBin(
                lower=float(edges[b]),
                upper=float(edges[b + 1]),
                count=count,
                mean_forecast=float(probabilities[mask].mean()),
                observed_frequency=float(labels[mask].mean()),
            )
        )
    return bins


def murphy_decomposition(
    labels: np.ndarray, probabilities: np.ndarray, n_bins: int = 10
) -> tuple[float, float, float]:
    """Split the Brier score into reliability, resolution and uncertainty.

        BS = reliability - resolution + uncertainty

    reliability  mean squared gap between forecast and observed frequency within
                 each bin. Lower is better; 0 means perfectly calibrated.
    resolution   how far bin frequencies depart from the overall base rate. Higher
                 is better; 0 means the forecast never distinguishes anything from
                 climatology.
    uncertainty  variance of the observations themselves. A property of the events,
                 not the forecast -- nothing a model does can change it.

    Worth computing because the two controllable terms fail differently and need
    different fixes: poor reliability is a calibration problem (isotonic
    recalibration helps), poor resolution is a signal problem (recalibration
    cannot help, only better predictors can).
    """
    n = len(labels)
    base_rate = float(labels.mean())
    uncertainty = base_rate * (1.0 - base_rate)

    reliability = 0.0
    resolution = 0.0
    for b in reliability_bins(labels, probabilities, n_bins):
        weight = b.count / n
        reliability += weight * (b.mean_forecast - b.observed_frequency) ** 2
        resolution += weight * (b.observed_frequency - base_rate) ** 2

    return reliability, resolution, uncertainty


def expected_calibration_error(
    labels: np.ndarray, probabilities: np.ndarray, n_bins: int = 10
) -> float:
    """Count-weighted mean absolute gap between forecast and observed frequency.

    The reliability diagram compressed to one number. Absolute rather than squared
    error, so the value reads directly as "on average our stated probability is
    off by this much" -- the form a non-specialist reviewer can interpret.
    """
    n = len(labels)
    return float(
        sum(
            (b.count / n) * abs(b.mean_forecast - b.observed_frequency)
            for b in reliability_bins(labels, probabilities, n_bins)
        )
    )


def sharpness(probabilities: np.ndarray) -> float:
    """Variance of the forecast probabilities.

    Reliability alone is trivially achieved by always predicting the base rate --
    perfectly calibrated, entirely useless. Sharpness is the counterweight, and
    the two must always be read together. Calibrated *and* sharp is the goal;
    either alone is not.
    """
    return float(np.var(probabilities))


def economic_value(labels: np.ndarray, probabilities: np.ndarray, cost_loss_ratio: float) -> float:
    """Potential economic value at one cost-loss ratio.

        V = (E_climatology - E_forecast) / (E_climatology - E_perfect)

    The standard cost-loss decision framework: a user pays cost C to protect
    against loss L, acts when forecast probability exceeds alpha = C/L, and V
    measures how much of the available saving the forecast captures. V = 1 is a
    perfect forecast, V = 0 is no better than acting on climatology alone, and
    negative means following the forecast is worse than ignoring it.

    This is the metric that turns a Brier score into something a farmer's decision
    depends on. Because V varies with alpha, `value_curve` sweeps it -- reporting
    a single V would let the choice of alpha flatter the forecast.
    """
    alpha = cost_loss_ratio
    base_rate = float(labels.mean())

    # Act whenever probability exceeds the cost-loss ratio. Optimal under the
    # standard framework, not a tuned choice.
    acted = probabilities > alpha
    hits = float(np.sum(acted & (labels == 1)))
    false_alarms = float(np.sum(acted & (labels == 0)))
    misses = float(np.sum(~acted & (labels == 1)))
    n = len(labels)

    expense_forecast = (hits * alpha + false_alarms * alpha + misses * 1.0) / n
    # Climatology: always act if alpha < base rate, otherwise never act.
    expense_climate = min(alpha, base_rate)
    expense_perfect = base_rate * alpha

    denominator = expense_climate - expense_perfect
    if abs(denominator) < 1e-12:
        return float("nan")
    return float((expense_climate - expense_forecast) / denominator)


def value_curve(
    labels: np.ndarray, probabilities: np.ndarray, n_points: int = 19
) -> list[tuple[float, float]]:
    """Economic value swept across cost-loss ratios from 0.05 to 0.95.

    The honest way to report decision value. A single number invites picking the
    alpha that flatters the model; the curve shows the range of users the forecast
    actually helps. For Ankur that maps onto a real spread -- a smallholder with no
    borewell, for whom a second seed bag is ruinous, sits at a very different alpha
    from an irrigated farm that can water through a spell.
    """
    ratios = np.linspace(0.05, 0.95, n_points)
    return [(float(a), economic_value(labels, probabilities, float(a))) for a in ratios]


def block_bootstrap_ci(
    labels: np.ndarray,
    probabilities: np.ndarray,
    groups: np.ndarray,
    *,
    statistic: str = "brier",
    reference: np.ndarray | None = None,
    n_resamples: int = 500,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Confidence interval from resampling whole seasons, not individual rows.

    A standard bootstrap resamples rows independently and would be badly wrong
    here. Rows are not independent: consecutive days share nearly all of their
    target window, and blocks within a district share weather. Resampling rows
    would treat ~10,000 correlated observations as ~10,000 independent ones and
    produce an interval several times too narrow -- the statistical version of the
    same mistake as quoting "34,000 block-days" as the sample size.

    Resampling by season (the `groups` argument) preserves within-season
    correlation and gives an interval reflecting how much the answer would move if
    a different set of monsoons had been observed.

    Args:
        groups: Season label per row. The resampling unit.
        statistic: "brier" or "bss"; "bss" requires `reference`.

    Returns:
        `(lower, upper)` percentile bounds.
    """
    rng = np.random.default_rng(RANDOM_SEED)
    unique_groups = np.unique(groups)
    # Precompute row positions per season so each resample is a concatenate rather
    # than a full boolean scan of the panel.
    positions = {g: np.flatnonzero(groups == g) for g in unique_groups}

    estimates: list[float] = []
    for _ in range(n_resamples):
        drawn = rng.choice(unique_groups, size=len(unique_groups), replace=True)
        index = np.concatenate([positions[g] for g in drawn])
        y, p = labels[index], probabilities[index]
        if statistic == "bss":
            if reference is None:
                raise ValueError("statistic='bss' requires a reference forecast")
            estimates.append(brier_skill_score(y, p, reference[index]))
        else:
            estimates.append(brier_score(y, p))

    finite = np.array([e for e in estimates if np.isfinite(e)])
    if finite.size == 0:
        return (float("nan"), float("nan"))
    tail = (1.0 - confidence) / 2.0
    return (float(np.quantile(finite, tail)), float(np.quantile(finite, 1.0 - tail)))


def evaluate(
    model_name: str,
    lead_days: int,
    labels: np.ndarray,
    probabilities: np.ndarray,
    reference: np.ndarray,
    *,
    n_bins: int = 10,
) -> VerificationResult:
    """Score one model at one lead against a reference forecast.

    `reference` is climatology's probabilities on the same rows -- passed in
    rather than recomputed, so every model in a run is scored against exactly the
    same denominator. Recomputing it per model is how skill scores quietly stop
    being comparable.
    """
    reliability, resolution, _ = murphy_decomposition(labels, probabilities, n_bins)

    # ROC-AUC is undefined when only one class is present, which happens in a
    # season with no dry spells at all. NaN is the honest answer.
    try:
        auc = float(roc_auc_score(labels, probabilities))
    except ValueError:
        auc = float("nan")

    return VerificationResult(
        model_name=model_name,
        lead_days=lead_days,
        n=len(labels),
        base_rate=float(labels.mean()),
        brier_score=brier_score(labels, probabilities),
        brier_skill_score=brier_skill_score(labels, probabilities, reference),
        reliability_error=reliability,
        resolution=resolution,
        expected_calibration_error=expected_calibration_error(labels, probabilities, n_bins),
        sharpness=sharpness(probabilities),
        roc_auc=auc,
        bins=tuple(reliability_bins(labels, probabilities, n_bins)),
    )
