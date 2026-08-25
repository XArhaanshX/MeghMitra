"""The model ladder: three baselines, then calibration. It stops at gradient boosting.

Every model here answers the same question -- "what is the probability a dry
spell begins in the next L days?" -- and exposes the same two methods, so
`evaluation.py` can score them identically. That uniformity is the point: the
load-forecasting benchmark's central lesson was that cross-family comparisons are
worthless unless every family sees identical preprocessing and identical scoring.

WHY THE LADDER STOPS WHERE IT DOES

Our own prior benchmark evaluated seventeen architectures across six families
(persistence, statistical, classical ML, deep learning, transformers, hybrid)
under one pipeline, and found a clean inverse relationship between architectural
complexity and accuracy: classical ML beat deep learning, which beat transformers,
with PatchTST needing 376x the training time to deliver twice the error. That was
on 245,000 rows. Here there are ~120 independent events. Adding an LSTM would
repeat an experiment whose answer we already have, with a hundredth of the data.

The literature agrees for this specific task. Extended logistic regression (Wilks
2009) and EMOS/NGR remain the reference post-processing methods for probabilistic
precipitation; published comparisons find the two roughly equal and both clearly
better than the raw ensemble, and recent subseasonal Indian-monsoon calibration
work still uses extended logistic regression as the baseline to beat rather than
as a legacy method. Neural post-processing does win at continental scale with
many years of reforecasts -- which is exactly the regime we are not in.

THE BASELINES ARE NOT DECORATION

B0 climatology is the denominator of every skill score reported. B2 -- the raw,
uncalibrated ensemble -- is the bar that decides whether this project has an ML
contribution at all. If calibration cannot beat simply counting ensemble members,
the honest report is that the ensemble is already well calibrated here and
Ankur's value lies entirely in the extraction and decision layers. That result
must be reportable, so the baseline is a first-class model, not a footnote.

LATENCY

All estimators are sklearn's compiled solvers on a panel of ~10^4 rows and 12
features. A full leave-one-season-out sweep across four leads and five models is
seconds, not minutes. No GPU, and no `fit` that outlasts the coffee.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Protocol, runtime_checkable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from trigger_engine.config import RANDOM_SEED
from trigger_engine.features import FEATURE_NAMES, MONOTONIC_CONSTRAINTS

# Probabilities are clipped away from exactly 0 and 1. A confident-and-wrong
# forecast at p = 0 is infinitely penalised by log score and, more practically, a
# system that ever says "certainly no dry spell" makes a promise no weather model
# can keep.
_PROBABILITY_FLOOR: Final[float] = 1e-4
_PROBABILITY_CEILING: Final[float] = 1.0 - 1e-4


@runtime_checkable
class ProbabilisticModel(Protocol):
    """The one interface every model on the ladder satisfies.

    Structural, not inherited -- the same `Protocol` approach
    `ankur_domain.repositories` uses, so a baseline that is really an array
    lookup need not pretend to be an estimator subclass.
    """

    name: str

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> ProbabilisticModel: ...

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray: ...


def _clip(probabilities: np.ndarray) -> np.ndarray:
    """Keep probabilities strictly inside (0, 1). See `_PROBABILITY_FLOOR`."""
    return np.clip(probabilities, _PROBABILITY_FLOOR, _PROBABILITY_CEILING)


# ---------------------------------------------------------------------------
# B0 -- climatology
# ---------------------------------------------------------------------------


class ClimatologyBaseline:
    """Predicts the historical base rate, varying by seasonal phase.

    The reference forecast for Brier Skill Score: BSS = 1 - BS/BS_clim, so a model
    with BSS <= 0 has added nothing over knowing the calendar.

    Conditioned on seasonal phase rather than a single flat rate. Dry-spell
    frequency varies substantially through JJAS -- June and late September are
    much drier than July -- so a flat rate is an artificially weak opponent, and
    beating a weak baseline proves nothing. The phase-varying version makes every
    reported skill number harder to earn and more honest.

    Phase is recovered from the `day_of_season_sin`/`cos` features rather than
    passed separately, so this baseline consumes exactly the same matrix as every
    other model on the ladder.

    `region_of_block`, when given, adds a region dimension to the binning: the
    reference rate for a block is estimated from its own region's history, not
    pooled nationally. Dry-spell climatology genuinely differs by region -- a
    Rajasthan block and a Kerala block do not share a base rate -- and pooling
    them would make the reference forecast, and therefore every downstream BSS,
    quietly wrong for a multi-region panel. `None` (the default) pools every
    block into one region, reproducing today's behaviour exactly.
    """

    name = "B0_climatology"

    def __init__(
        self,
        n_bins: int = 12,
        *,
        region_of_block: Mapping[str, str] | None = None,
    ) -> None:
        # ~10-day bins across a 122-day season: fine enough to track the seasonal
        # cycle, coarse enough that each bin pools enough seasons to estimate a
        # rate rather than reproduce one season's noise.
        self.n_bins = n_bins
        self.region_of_block = region_of_block
        self._rates: np.ndarray | None = None
        self._region_rates: dict[str, np.ndarray] | None = None
        self._overall: float = 0.0

    @staticmethod
    def _phase_bin(features: pd.DataFrame, n_bins: int) -> np.ndarray:
        """Recover day-of-season phase from its sin/cos pair, then bin it."""
        angle = np.arctan2(features["day_of_season_sin"], features["day_of_season_cos"])
        normalized = (angle % (2 * np.pi)) / (2 * np.pi)
        return np.minimum((normalized * n_bins).astype(int), n_bins - 1)

    @staticmethod
    def _fit_bin_rates(
        bins: np.ndarray, labels: np.ndarray, n_bins: int, overall: float
    ) -> np.ndarray:
        """Per-bin rate, falling back to `overall` for a thinly-populated bin."""
        rates = np.full(n_bins, overall, dtype=float)
        for b in range(n_bins):
            mask = bins == b
            # Require a few observations before trusting a bin-specific rate;
            # otherwise fall back to the pooled rate rather than to noise.
            if mask.sum() >= 10:
                rates[b] = labels[mask].mean()
        return rates

    def _regions_for(self, blocks: pd.Series) -> np.ndarray:
        assert self.region_of_block is not None
        return np.array([self.region_of_block.get(b, b) for b in blocks.to_numpy()])

    def fit(
        self,
        features: pd.DataFrame,
        labels: np.ndarray,
        *,
        blocks: pd.Series | None = None,
    ) -> ClimatologyBaseline:
        bins = self._phase_bin(features, self.n_bins)
        self._overall = float(labels.mean()) if len(labels) else 0.0
        self._rates = self._fit_bin_rates(bins, labels, self.n_bins, self._overall)

        if self.region_of_block is None:
            self._region_rates = None
        else:
            if blocks is None:
                raise ValueError(
                    "ClimatologyBaseline(region_of_block=...) requires blocks= at fit time"
                )
            regions = self._regions_for(blocks)
            self._region_rates = {
                region: self._fit_bin_rates(
                    bins[regions == region], labels[regions == region], self.n_bins, self._overall
                )
                for region in np.unique(regions)
            }
        return self

    def predict_proba(
        self,
        features: pd.DataFrame,
        *,
        blocks: pd.Series | None = None,
    ) -> np.ndarray:
        if self._rates is None:
            raise RuntimeError("ClimatologyBaseline.predict_proba called before fit")
        bins = self._phase_bin(features, self.n_bins)
        if self._region_rates is None:
            return _clip(self._rates[bins])
        if blocks is None:
            raise ValueError(
                "ClimatologyBaseline was fit with region_of_block=...; predict_proba needs "
                "blocks= too"
            )
        regions = self._regions_for(blocks)
        out = np.array(
            [
                self._region_rates.get(region, self._rates)[b]
                for region, b in zip(regions, bins, strict=True)
            ]
        )
        return _clip(out)


# ---------------------------------------------------------------------------
# B1 -- persistence
# ---------------------------------------------------------------------------


class PersistenceBaseline:
    """ "It is dry now, so it will stay dry." Included to be beaten.

    Persistence won our load-forecasting benchmark outright (1.63% MAPE, best of
    seventeen models) because 15-minute electricity demand is overwhelmingly
    autocorrelated at lag 1. Daily rainfall is not: autocorrelation decays to near
    zero within about two days, so persistence should perform poorly at 7-30 day
    leads.

    Keeping it on the ladder is deliberate. It makes the difference between the
    two problems measurable rather than asserted, and guards against quietly
    importing the previous project's conclusion into a domain where it does not
    hold.
    """

    name = "B1_persistence"

    def __init__(self, dry_run_threshold: int = 3) -> None:
        self.dry_run_threshold = dry_run_threshold
        self._rate_if_dry = 0.5
        self._rate_if_wet = 0.5

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> PersistenceBaseline:
        currently_dry = (features["dry_run_lag1"] >= self.dry_run_threshold).to_numpy()
        # Empirical conditional rates rather than a hard 0/1: even persistence
        # should emit a probability, so it can be scored on the same axis as
        # everything else.
        self._rate_if_dry = float(labels[currently_dry].mean()) if currently_dry.any() else 0.5
        self._rate_if_wet = float(labels[~currently_dry].mean()) if (~currently_dry).any() else 0.5
        return self

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        currently_dry = (features["dry_run_lag1"] >= self.dry_run_threshold).to_numpy()
        return _clip(np.where(currently_dry, self._rate_if_dry, self._rate_if_wet))


# ---------------------------------------------------------------------------
# B2 -- raw ensemble
# ---------------------------------------------------------------------------


class RawEnsembleBaseline:
    """The uncalibrated ensemble dry-member fraction, used directly as a probability.

    This is the bar that matters. Operational ensembles are typically
    under-dispersive -- overconfident, with member spread understating true
    uncertainty -- which is the entire reason statistical post-processing exists
    as a field. But "usually miscalibrated" is not "miscalibrated here", and the
    only way to know is to score it.

    `fit` intentionally does nothing. There is no training: this model is a
    passthrough, and writing it as a no-op makes that visible in the results table
    where a train-time of 0.00 tells its own story.
    """

    name = "B2_raw_ensemble"

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> RawEnsembleBaseline:
        return self

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        return _clip(features["ens_dry_fraction"].to_numpy(dtype=float))


# ---------------------------------------------------------------------------
# M1a -- extended logistic regression
# ---------------------------------------------------------------------------


class ExtendedLogisticRegression:
    """Wilks-style extended logistic regression, extended over *spell length*.

    Standard logistic regression fits one model per threshold, with two
    well-documented drawbacks: the parameter count multiplies, and separately
    fitted curves can cross, producing the incoherent claim that a 15-day spell is
    more likely than a 5-day one. Wilks (2009) made the threshold itself a
    predictor, so one fit yields a coherent family of curves. Published
    comparisons also find the extended form beats separate fits specifically when
    the training period is *short* -- which is our regime exactly.

    Here the threshold axis is dry-spell *length* in days, which solves a real
    problem in this project rather than a hypothetical one. We calibrate against
    5-day spells because they are frequent enough to estimate reliably, but the
    Sirsa DACP rule is written for a 15-20 day spell. Separate models would give
    two unrelated numbers with no guarantee the longer spell scores lower. This
    gives P(spell >= g) for any g from a single fit, monotone in g by
    construction.

    Functional form:

        logit P(L >= g | x) = x'beta - gamma * sqrt(g)

    `sqrt(g)` follows the square-root link Wilks used for precipitation amounts.
    Coherence requires the coefficient on that term to be negative; it is checked
    rather than assumed -- see `coherence_violation`.
    """

    name = "M1a_extended_logistic"

    def __init__(self, thresholds: tuple[int, ...] = (3, 5, 7, 10, 15)) -> None:
        self.thresholds = thresholds
        self._model = LogisticRegression(
            max_iter=1000,
            # L2 at moderate strength. On ~120 independent events an unregularized
            # fit over 13 columns will happily find structure that is not there.
            C=1.0,
            solver="lbfgs",
            random_state=RANDOM_SEED,
        )
        self._scaler = StandardScaler()
        self._fitted = False

    @staticmethod
    def _threshold_term(threshold: float) -> float:
        """The sqrt(g) link. Isolated so the transform can be swapped in one place."""
        return float(np.sqrt(threshold))

    def fit_extended(
        self,
        features: pd.DataFrame,
        labels_by_threshold: dict[int, np.ndarray],
    ) -> ExtendedLogisticRegression:
        """Fit across all spell-length thresholds at once.

        The design matrix is the feature matrix stacked once per threshold, with
        the threshold term appended as an extra column. Every observation
        contributes one row per threshold, and a single coefficient vector is
        shared across all of them -- which is what forces the curves to stay
        parallel and non-crossing.

        Args:
            features: Causal feature matrix.
            labels_by_threshold: Maps spell length g -> binary labels for "a spell
                of at least g days begins in the window".
        """
        scaled = self._scaler.fit_transform(features[list(FEATURE_NAMES)].to_numpy(dtype=float))

        blocks, targets = [], []
        for threshold, labels in labels_by_threshold.items():
            term = np.full((len(scaled), 1), self._threshold_term(threshold))
            blocks.append(np.hstack([scaled, term]))
            targets.append(labels)

        self._model.fit(np.vstack(blocks), np.concatenate(targets))
        self._fitted = True
        return self

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> ExtendedLogisticRegression:
        """Single-threshold convenience fit, so ELR slots into the shared ladder.

        Degenerates to ordinary logistic regression with a constant threshold
        column. Use `fit_extended` for the coherent multi-length family this class
        exists to provide.
        """
        return self.fit_extended(features, {5: labels})

    def predict_proba_at(self, features: pd.DataFrame, threshold: int) -> np.ndarray:
        """P(spell of at least `threshold` days begins in the window)."""
        if not self._fitted:
            raise RuntimeError("ExtendedLogisticRegression.predict_proba called before fit")
        scaled = self._scaler.transform(features[list(FEATURE_NAMES)].to_numpy(dtype=float))
        term = np.full((len(scaled), 1), self._threshold_term(threshold))
        return _clip(self._model.predict_proba(np.hstack([scaled, term]))[:, 1])

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        """Probability at the 5-day threshold, the ladder's common target."""
        return self.predict_proba_at(features, 5)

    @property
    def coherence_violation(self) -> bool:
        """True if longer spells were fitted as *more* likely -- an incoherent fit.

        The coefficient on the sqrt(g) column must be negative. A positive one
        claims a 15-day dry spell is likelier than a 5-day one, which is
        impossible by construction since every 15-day spell contains a 5-day one.
        Surfaced as a property rather than raising, because it is a diagnostic
        about the data (usually too few long-spell positives), not a bug.
        """
        if not self._fitted:
            return False
        return bool(self._model.coef_[0][-1] > 0)


# ---------------------------------------------------------------------------
# M1c -- gradient boosting with monotonic constraints
# ---------------------------------------------------------------------------


class GradientBoostedCalibrator:
    """Histogram gradient boosting, constrained to physically sensible directions.

    Chosen over LightGBM/XGBoost purely to avoid a dependency: sklearn's
    implementation is the same LightGBM-style histogram algorithm, is compiled,
    and supports the monotonic constraints this problem needs. One less package on
    a demo laptop is worth more than a marginal speed difference.

    `MONOTONIC_CONSTRAINTS` is what makes a tree model defensible at this sample
    size. Unconstrained, a boosted model on ~120 events will find non-monotone
    wiggles in the ensemble-fraction response that are pure noise, and an
    agronomist reading the partial dependence plot would be right to reject it.
    Constrained, it can still learn interaction structure a linear model cannot,
    but it cannot learn that more forecast dryness means less risk.

    Kept shallow (`max_depth=3`) and early-stopped for the same reason.
    """

    name = "M1c_gradient_boosted"

    def __init__(self, max_depth: int = 3, max_iter: int = 200) -> None:
        constraints = [MONOTONIC_CONSTRAINTS.get(feature, 0) for feature in FEATURE_NAMES]
        self._model = HistGradientBoostingClassifier(
            max_depth=max_depth,
            max_iter=max_iter,
            learning_rate=0.05,
            monotonic_cst=constraints,
            early_stopping=True,
            n_iter_no_change=20,
            validation_fraction=0.15,
            random_state=RANDOM_SEED,
        )

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> GradientBoostedCalibrator:
        self._model.fit(features[list(FEATURE_NAMES)].to_numpy(dtype=float), labels)
        return self

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        raw = self._model.predict_proba(features[list(FEATURE_NAMES)].to_numpy(dtype=float))
        return _clip(raw[:, 1])


# ---------------------------------------------------------------------------
# M1d -- isotonic recalibration
# ---------------------------------------------------------------------------


class IsotonicRecalibrator:
    """Wraps any model and re-maps its probabilities onto observed frequencies.

    Boosted trees optimise a proper scoring rule but still routinely emit
    probabilities whose reliability curve departs from the diagonal. Isotonic
    regression fits a non-decreasing step function from predicted to observed
    frequency, correcting calibration while leaving the *ranking* -- and therefore
    ROC-AUC -- untouched.

    Isotonic rather than Platt scaling: Platt assumes a sigmoid distortion, right
    when miscalibration is simple over- or under-confidence. Isotonic makes no
    shape assumption and handles the flat-then-steep curves ensemble-derived
    probabilities typically show. The cost is a tendency to overfit on small
    samples, mitigated by fitting on out-of-fold predictions only -- fitting it on
    rows the base model trained on would merely relearn that model's overfit.
    """

    name = "M1d_isotonic"

    def __init__(self, base: ProbabilisticModel) -> None:
        self.base = base
        self.name = f"M1d_isotonic({base.name})"
        self._isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self._fitted = False

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> IsotonicRecalibrator:
        """Fit the base model, then fit the correction on its own predictions.

        The correction is fitted in-sample here, for interface compatibility only.
        `pipeline.py` uses `fit_correction` with genuinely held-out predictions,
        which is the only statistically sound way to use this.
        """
        self.base.fit(features, labels)
        self._isotonic.fit(self.base.predict_proba(features), labels)
        self._fitted = True
        return self

    def fit_correction(self, held_out_probabilities: np.ndarray, labels: np.ndarray) -> None:
        """Fit only the isotonic map, from out-of-fold predictions. Preferred."""
        self._isotonic.fit(held_out_probabilities, labels)
        self._fitted = True

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        raw = self.base.predict_proba(features)
        return _clip(self._isotonic.predict(raw)) if self._fitted else raw


def default_ladder() -> list[ProbabilisticModel]:
    """The models scored on every run, in increasing order of complexity.

    Ordered deliberately: results tables read top to bottom, and a reader should
    see what the simple options achieve before meeting the complicated one.
    """
    return [
        ClimatologyBaseline(),
        PersistenceBaseline(),
        RawEnsembleBaseline(),
        ExtendedLogisticRegression(),
        GradientBoostedCalibrator(),
    ]
