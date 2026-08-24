"""Dry-spell targets.

The label is the one thing in a forecasting pipeline that must be defined before
anything else and never quietly changed afterwards, because every score is
relative to it. A model that looks better after a label tweak has usually just
been given an easier question.

Definition, fixed here and versioned by `LABEL_VERSION`:

    dry_day   := daily rainfall < 2.5 mm             (IMD's rainy-day threshold)
    dry_spell := >= N consecutive dry_days           (N = DRY_SPELL_MIN_DAYS)
    y(t, L)   =  1 if a dry_spell *begins* within [t+1, t+L]

Two details that are easy to get wrong and that change what is being measured:

*begins*, not *occurs*. If we labelled "a spell is in progress during the
window", then a spell already underway at time t would label the next thirty days
positive, and a model could score highly by reporting the present rather than
forecasting. Onset-within-window is the decision-relevant question anyway: the
farmer needs to know whether a dry spell is *coming*, not whether one is here.

t+1, not t. The window opens strictly after the issue date, so nothing about day
t itself is in the target. Combined with features that read only t-1 and earlier
(`features.py`), this leaves a clean one-day gap between predictor and target.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

from trigger_engine.config import (
    COL_BLOCK,
    COL_RAIN,
    COL_RAIN_IMPUTED,
    DRY_SPELL_MIN_DAYS,
    RAINY_DAY_THRESHOLD_MM,
)

LABEL_VERSION: Final[str] = "dryspell/1.0.0"
"""Bump on any change to the definitions above. Scores computed under different
label versions are not comparable, and a version string is the cheapest way to
stop someone comparing them anyway."""


def _reverse_rolling(values: pd.Series, blocks: pd.Series, window: int, how: str) -> pd.Series:
    """Forward-looking rolling aggregate, computed per block.

    pandas rolls backwards, so a forward window is a reverse-roll-reverse. This
    is factored out because getting the index handling wrong here silently
    misaligns labels by one row, which is undetectable in aggregate metrics and
    catastrophic for them.

    `min_periods=window` makes a truncated window at the end of each block's
    record produce NaN rather than a partial result -- a spell cannot be confirmed
    using days that are not in the record.
    """
    reversed_groups = blocks[::-1]
    rolled = getattr(
        values[::-1].groupby(reversed_groups, sort=False).rolling(window, min_periods=window),
        how,
    )()
    return rolled.reset_index(level=0, drop=True)[::-1]


def dry_spell_starts(frame: pd.DataFrame, *, min_days: int = DRY_SPELL_MIN_DAYS) -> pd.Series:
    """Boolean per row: does a dry spell of `min_days` *begin* on this day?

    A spell begins on day t when t is dry, the previous day was not dry (so this
    is the first day of a run rather than a continuation), and the next
    `min_days` days including t are all dry.

    Uses a forward-looking window, which is legitimate here precisely because
    this is the *target*: labels may see the future, features may not. That
    asymmetry is the entire reason this module is separate from `features.py`.

    Days whose rainfall was never observed produce NaN rather than False.
    Treating an unobserved day as "no spell started" would teach the model that
    data gaps are safe, and gaps correlate with bad weather.
    """
    is_dry = frame[COL_RAIN] < RAINY_DAY_THRESHOLD_MM
    blocks = frame[COL_BLOCK]

    forward_dry_run = _reverse_rolling(is_dry.astype(float), blocks, min_days, "sum")

    previous_day_dry = is_dry.groupby(blocks, sort=False).shift(1)
    # The first day of a block's record has no predecessor; treat it as "not a
    # continuation" so a spell starting on day one still counts.
    is_run_start = ~previous_day_dry.fillna(False).astype(bool)

    starts = (forward_dry_run >= min_days) & is_run_start

    # Any window touching an unobserved rainfall day is unlabelable.
    unobserved_in_window = _reverse_rolling(
        frame[COL_RAIN_IMPUTED].astype(float), blocks, min_days, "max"
    )

    return starts.where(forward_dry_run.notna() & (unobserved_in_window == 0))


def build_labels(
    frame: pd.DataFrame,
    *,
    lead_days: int,
    min_days: int = DRY_SPELL_MIN_DAYS,
) -> pd.Series:
    """y(t, L): does a dry spell begin anywhere in (t, t+L]?

    Args:
        frame: Panel sorted by (block, date), carrying `COL_RAIN` and
            `COL_RAIN_IMPUTED`.
        lead_days: L, the forecast horizon in days.
        min_days: Spell length that counts. Adjustable so the same code builds
            both the frequent 5-day target we calibrate on and the rare 15-20 day
            target the Sirsa rule names -- see `config.DRY_SPELL_MIN_DAYS` for
            why those differ.

    Returns:
        Float series in {0.0, 1.0}, NaN where the window cannot be labelled (end
        of record, or an unobserved rainfall day inside it). NaN rather than 0 so
        callers must drop explicitly: a silent zero is an invented negative.

    The rolled window is shifted by -1 so it covers t+1..t+L and excludes day t.
    """
    starts = dry_spell_starts(frame, min_days=min_days)
    blocks = frame[COL_BLOCK]
    future_starts = _reverse_rolling(starts.astype(float), blocks, lead_days, "max")
    return future_starts.groupby(blocks, sort=False).shift(-1).astype(float)


def label_base_rate(labels: pd.Series) -> float:
    """Fraction of labelable rows that are positive.

    Reported everywhere a skill score is reported. A Brier score of 0.05 sounds
    excellent until you learn the base rate is 0.05, at which point predicting
    the climatological constant achieves the same thing. This number is what
    makes a skill score interpretable, and `evaluation.py` will not print one
    without it.
    """
    clean = labels.dropna()
    return float(clean.mean()) if len(clean) else float("nan")


def effective_sample_size(
    labels: pd.Series,
    seasons: pd.Series,
    *,
    lead_days: int,
    blocks: pd.Series | None = None,
) -> dict[str, float]:
    """Honest accounting of how much independent information the labels carry.

    Raw row counts badly overstate it, in two compounding ways, and both must be
    divided out or the number is worse than useless -- it is confidently wrong.

    1. **Window overlap.** At L = 14, adjacent rows share 13 of their 14 target
       days, so roughly `lead_days` consecutive rows describe one event. Dividing
       by `lead_days` (not by spell length, which is a different quantity) is what
       converts overlapping rows into approximate events.

    2. **Spatial correlation.** Blocks within one district see the same synoptic
       systems; when it is dry in Sirsa it is dry in Ellenabad. Seven blocks is
       far closer to one spatial sample than to seven, so the block count is
       divided out entirely. That is conservative rather than exact -- the true
       figure is somewhere between 1 and N -- and conservative is the right
       direction for a number whose purpose is to restrain over-claiming.

    A deliberately pessimistic approximation. Its job is to stop anyone quoting
    "34,000 block-days" as though it were 34,000 samples, which would make every
    confidence interval several times too narrow. `seasons` is reported alongside
    because the season is the only axis along which samples are genuinely
    independent, and it is what `evaluation.block_bootstrap_ci` resamples over.
    """
    clean = labels.dropna()
    positives = float(clean.sum())
    n_blocks = float(blocks.loc[clean.index].nunique()) if blocks is not None else 1.0

    independent = positives / max(lead_days, 1) / max(n_blocks, 1.0)
    return {
        "rows": float(len(clean)),
        "positives": positives,
        "seasons": float(seasons.loc[clean.index].nunique()),
        "blocks": n_blocks,
        "approx_independent_events": independent,
    }


def drop_unlabelable(features: pd.DataFrame, labels: pd.Series) -> tuple[pd.DataFrame, np.ndarray]:
    """Align a feature frame to its labels, dropping rows that cannot be scored.

    Rows go when the label is NaN (unobservable window) or any feature is NaN
    (insufficient history, or a missing forecast cycle). Returned as a
    `(DataFrame, ndarray)` pair sharing one row order, so downstream sklearn
    calls need no further alignment -- silently misaligned X and y is an easy and
    severe mistake to make with pandas.
    """
    usable = labels.notna() & features.notna().all(axis=1)
    return features.loc[usable], labels.loc[usable].to_numpy(dtype=float)
