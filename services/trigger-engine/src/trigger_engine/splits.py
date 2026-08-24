"""Leave-one-monsoon-season-out cross-validation.

The season is the only axis along which samples here are close to independent.
Rows within a season are not: consecutive days share most of their target window,
and blocks within a district see the same synoptic systems. A random split would
put day 12 of a season in training and day 13 in test, which is not validation --
it is asking the model to interpolate a curve it has already seen.

Why leave-one-season-out rather than the single chronological tail split the
load-forecasting paper used: that paper held out one final year from 245,000
rows, which is defensible when the test partition still holds 35,040
observations. Here one held-out season contains roughly three independent dry
spells, so a single split produces a skill score with no usable error bar.
Rotating through every season gives one score per season and therefore a
distribution -- which is what `evaluation.block_bootstrap_ci` needs to say
anything honest about uncertainty.

The final held-out season (2025 in the demo) stays *outside* this rotation. It is
narrative for the demo; the cross-validated distribution is the evidence.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class SeasonFold:
    """One cross-validation fold, addressed by season rather than by row index.

    Carrying the season numbers (not just boolean masks) is deliberate: every fit
    that must be restricted to training data -- the climatology in
    `features.pentad_climatology`, the scaler, the water-balance parameters --
    takes a season set as its argument. Passing the same object to all of them is
    what stops the folds and the fits from drifting apart.
    """

    test_season: int
    train_seasons: frozenset[int]
    train_index: np.ndarray
    test_index: np.ndarray

    def __repr__(self) -> str:
        return (
            f"SeasonFold(test={self.test_season}, "
            f"n_train={len(self.train_index)}, n_test={len(self.test_index)})"
        )


def season_folds(
    seasons: pd.Series,
    *,
    holdout_seasons: frozenset[int] = frozenset(),
    min_train_seasons: int = 3,
) -> Iterator[SeasonFold]:
    """Yield one fold per season, each holding that season out entirely.

    Args:
        seasons: Season label per row, aligned to the feature matrix.
        holdout_seasons: Seasons excluded from the rotation altogether -- neither
            trained on nor tested on. This is where the final demo-year hold-out
            goes, so it cannot leak into model selection through repeated
            evaluation.
        min_train_seasons: Skip folds with fewer training seasons than this. With
            one or two seasons the climatology is meaningless and the fold's score
            says more about the estimator's variance than the model's skill.

    Yields:
        `SeasonFold`s in ascending season order.

    Deliberately *not* a forward-chaining / expanding-window split. Forward
    chaining is right when the data-generating process drifts and only past data
    may inform the future. Here the target is a near-stationary climatological
    process, so withholding earlier seasons would shrink an already tiny training
    set for no benefit. What must never happen is one season appearing on both
    sides of a fold, and that is what this enforces.
    """
    unique = sorted(set(seasons.unique().tolist()) - set(holdout_seasons))
    positions = np.arange(len(seasons))
    season_values = seasons.to_numpy()

    for test_season in unique:
        train_seasons = frozenset(int(s) for s in unique if s != test_season)
        if len(train_seasons) < min_train_seasons:
            continue
        test_mask = season_values == test_season
        train_mask = np.isin(season_values, list(train_seasons))
        yield SeasonFold(
            test_season=int(test_season),
            train_seasons=train_seasons,
            train_index=positions[train_mask],
            test_index=positions[test_mask],
        )


def chronological_holdout(seasons: pd.Series, *, n_holdout: int = 1) -> frozenset[int]:
    """The last `n_holdout` seasons, reserved as a final untouched test set.

    Separate from the cross-validation rotation on purpose. Every time a model is
    evaluated against the same data, a little of that data's information leaks
    into the choices that follow -- which model, which features, which threshold.
    A hold-out touched once, at the end, is the only one that can honestly be
    called out-of-sample.
    """
    unique = sorted(seasons.unique().tolist())
    return frozenset(int(s) for s in unique[-n_holdout:]) if unique else frozenset()
