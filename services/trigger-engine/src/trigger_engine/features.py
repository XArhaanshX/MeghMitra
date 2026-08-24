"""Causal predictors for the dry-spell model.

Every feature here is built from data available strictly *before* the day it
describes. That is enforced structurally rather than by convention: each feature
is declared in `FEATURE_SPECS` with the shift it applies, and
`tests/unit/test_causality.py` re-derives every column against a truncated panel
to confirm that a feature computed on day t is unchanged when all data from t
onward is deleted. A leaked feature produces a beautiful validation score and a
worthless forecast, and it is nearly undetectable by eye.

Feature groups, retargeted from the 45-feature load-forecasting set. The mapping
is not one-to-one, because the two problems have different structure:

    load pipeline                      here
    -----------------------------------------------------------------
    lags 1..672 (15-min steps)         rain lags 1,2,3,5,7,10,15,30 (days)
    rolling mean/std/min/max @4,96,672 rain sum/max/dry-count @3,7,15,30
    Fourier P=96 (day), P=672 (week)   Fourier P=122 (season) only
    cyclical hour, day-of-week         day-of-season sin/cos
    day-over-day ratio                 rain / pentad climatological normal
    (none)                             soil-moisture state from FAO-56 bucket
    (none)                             ensemble dry-fraction  <- strongest input
    (none)                             ENSO / IOD / MJO lagged teleconnections

The two "(none)" rows are where most of the skill lives, and neither has an
analogue in the load problem. Diurnal and weekly harmonics are dropped outright:
there is no meaningful hour or day-of-week structure in daily block rainfall, and
carrying them would add parameters that can only fit noise.

Target width is ~12 columns. The load paper used 45 features against 245,000
rows; here there are on the order of 120 independent events (see
`labels.effective_sample_size`), so 45 features would be fitting noise with high
confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from trigger_engine.config import (
    COL_BLOCK,
    COL_DATE,
    COL_ENS_DRY_FRACTION,
    COL_RAIN,
    MONSOON_START_DAY,
    MONSOON_START_MONTH,
    RAINY_DAY_THRESHOLD_MM,
)

RAIN_LAG_DAYS: Final[tuple[int, ...]] = (1, 2, 3, 5, 7, 10, 15, 30)
"""Multi-scale lags available to feature builders. 1-3 days captures synoptic
persistence, 5-10 the active/break cycle of the monsoon intraseasonal
oscillation, 15-30 the slower MISO envelope that carries most subseasonal
predictability over South Asia."""

ROLLING_WINDOWS: Final[tuple[int, ...]] = (3, 7, 15, 30)
"""Accumulation windows. 7 and 15 straddle the dry-spell lengths the DACP uses;
30 is roughly the MISO period."""

SEASON_LENGTH_DAYS: Final[int] = 122
"""June 1 - September 30. The only Fourier period that means anything here."""


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    """Declaration of one feature column and how far back it reads.

    `min_shift_days` is the lag applied before any window: 1 means the feature
    cannot see day t at all. Tests read this to verify causality mechanically
    rather than trusting the implementation.
    """

    name: str
    min_shift_days: int
    group: str
    rationale: str


FEATURE_SPECS: Final[tuple[FeatureSpec, ...]] = (
    FeatureSpec(
        "sm_frac_lag1",
        1,
        "water_balance",
        "Root-zone wetness yesterday. The physical state variable that separates "
        "a meteorological dry spell from an agricultural one.",
    ),
    FeatureSpec(
        "sm_frac_delta_7d",
        1,
        "water_balance",
        "Change in wetness over the past week: direction of travel, not level.",
    ),
    FeatureSpec(
        "dry_run_lag1",
        1,
        "water_balance",
        "Dry days already accumulated. A spell in progress raises the odds the "
        "next window also contains one.",
    ),
    FeatureSpec(
        "ens_dry_fraction",
        0,
        "ensemble",
        "Share of ensemble members forecasting a dry spell. Already a raw "
        "probability, and the baseline any calibration must beat. Shift 0 is "
        "correct and not a leak: a forecast issued on day t is available on day t "
        "by construction.",
    ),
    FeatureSpec(
        "rain_sum_7d",
        1,
        "rainfall",
        "Recent accumulation. Wet antecedent conditions delay agricultural stress "
        "even after rainfall stops.",
    ),
    FeatureSpec("rain_sum_30d", 1, "rainfall", "Season-to-date supply, the slow component."),
    FeatureSpec(
        "dry_days_15d",
        1,
        "rainfall",
        "Dry-day count over the past fortnight. Frequency rather than volume, "
        "which is what the dry-spell definition is actually about.",
    ),
    FeatureSpec(
        "rain_anomaly_15d",
        1,
        "anomaly",
        "Departure from pentad climatology, standardized, so the feature is "
        "comparable across blocks with very different mean rainfall.",
    ),
    FeatureSpec(
        "day_of_season_sin",
        0,
        "calendar",
        "Seasonal phase. Dry-spell risk is strongly non-uniform through JJAS, and "
        "phase is known in advance, so there is no leak.",
    ),
    FeatureSpec(
        "day_of_season_cos",
        0,
        "calendar",
        "Cosine partner: together these keep June 1 and September 30 far apart in "
        "feature space while adjacent days stay adjacent.",
    ),
    FeatureSpec(
        "oni_lag30",
        30,
        "teleconnection",
        "ENSO state, lagged. Required by the problem statement, and El Nino years "
        "carry materially higher Indian monsoon break risk.",
    ),
    FeatureSpec(
        "mjo_amplitude_lag10",
        10,
        "teleconnection",
        "MJO/MISO amplitude, lagged. The dominant source of genuine subseasonal "
        "skill over South Asia at 10-30 day leads.",
    ),
)

FEATURE_NAMES: Final[tuple[str, ...]] = tuple(spec.name for spec in FEATURE_SPECS)

MONOTONIC_CONSTRAINTS: Final[dict[str, int]] = {
    "ens_dry_fraction": +1,
    "dry_run_lag1": +1,
    "dry_days_15d": +1,
    "sm_frac_lag1": -1,
    "rain_sum_7d": -1,
}
"""Sign constraints passed to the gradient-boosted model.

Not tuning knobs -- physics we already know. More ensemble members forecasting
dryness cannot *lower* the probability of a dry spell; a wetter profile cannot
*raise* it. Encoding this does three things at once: regularizes hard on a small
sample, keeps the model explicable to an agronomist, and makes the decision
layer's threshold behaviour monotone, so a farmer who sees a higher probability
never receives a less cautious recommendation.
"""


def _grouped_shift(values: pd.Series, blocks: pd.Series, periods: int) -> pd.Series:
    """Shift within each block. The primitive every causal feature is built on."""
    return values.groupby(blocks, sort=False).shift(periods)


def _grouped_rolling(
    values: pd.Series, blocks: pd.Series, window: int, how: str, *, shift: int = 1
) -> pd.Series:
    """Backward rolling aggregate applied to already-shifted values.

    The shift happens *before* the roll, exactly as in the load-forecasting
    pipeline where every rolling statistic was computed on L_{t-1}. Rolling first
    and shifting after would put day t inside the window and leak the present.
    """
    shifted = _grouped_shift(values, blocks, shift)
    rolled = getattr(shifted.groupby(blocks, sort=False).rolling(window, min_periods=window), how)()
    return rolled.reset_index(level=0, drop=True)


def pentad_climatology(frame: pd.DataFrame, *, training_seasons: set[int]) -> pd.DataFrame:
    """Mean and standard deviation of pentad rainfall, by block.

    **Fitted on training seasons only.** This is the subtlest leak in the whole
    pipeline: climatological normals feel like a fixed property of a place, so it
    is natural to compute them once over the full record. Doing that puts
    test-season rainfall into a feature used to predict the test season. Normals
    must be refitted inside every cross-validation fold, which is why this takes
    an explicit `training_seasons` argument rather than reading the frame's span.

    Pentads (5-day blocks) rather than days: a day-resolution climatology over ~40
    seasons rests on 40 numbers per block per day and is mostly noise. Pentads
    pool five times more data for a curve this smooth.
    """
    working = frame[[COL_BLOCK, COL_DATE, COL_RAIN]].copy()
    working["season"] = working[COL_DATE].dt.year
    working["pentad"] = ((working[COL_DATE].dt.dayofyear - 1) // 5).astype(int)

    train = working[working["season"].isin(training_seasons)]
    stats = (
        train.groupby([COL_BLOCK, "pentad"])[COL_RAIN]
        .agg(["mean", "std"])
        .rename(columns={"mean": "pentad_rain_mean", "std": "pentad_rain_std"})
        .reset_index()
    )
    # A block-pentad seen only once has std NaN; fall back to the block's overall
    # spread rather than dropping the row.
    fallback = train.groupby(COL_BLOCK)[COL_RAIN].std().rename("block_rain_std").reset_index()
    stats = stats.merge(fallback, on=COL_BLOCK, how="left")
    stats["pentad_rain_std"] = stats["pentad_rain_std"].fillna(stats["block_rain_std"])
    return stats.drop(columns="block_rain_std")


def build_features(
    frame: pd.DataFrame,
    *,
    training_seasons: set[int],
    teleconnections: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Assemble the causal feature matrix.

    Args:
        frame: Panel after `waterbalance.run_water_balance`, sorted by
            (block, date).
        training_seasons: Seasons the climatology may be fitted on. Must exclude
            every season being predicted.
        teleconnections: Optional frame with `date`, `oni`, `mjo_amplitude`.
            Absent, those columns are 0.0 (a neutral standardized index) so the
            pipeline runs end-to-end without them and the model simply finds no
            signal there.

    Returns:
        A frame whose columns are exactly `FEATURE_NAMES`, indexed like `frame`.
        NaN rows (insufficient history) are left in place; `labels.drop_unlabelable`
        removes them once labels are known, so features and labels are dropped
        together and stay aligned.

    Vectorized throughout -- one pass per feature, no row loops, no `apply`. A
    40-season, 7-block panel builds in well under a second.
    """
    blocks = frame[COL_BLOCK]
    out = pd.DataFrame(index=frame.index)

    # --- water balance state -------------------------------------------------
    out["sm_frac_lag1"] = _grouped_shift(frame["soil_moisture_fraction"], blocks, 1)
    out["sm_frac_delta_7d"] = out["sm_frac_lag1"] - _grouped_shift(
        frame["soil_moisture_fraction"], blocks, 8
    )
    out["dry_run_lag1"] = _grouped_shift(frame["consecutive_dry_days"], blocks, 1)

    # --- rainfall history ----------------------------------------------------
    out["rain_sum_7d"] = _grouped_rolling(frame[COL_RAIN], blocks, 7, "sum")
    out["rain_sum_30d"] = _grouped_rolling(frame[COL_RAIN], blocks, 30, "sum")
    is_dry = (frame[COL_RAIN] < RAINY_DAY_THRESHOLD_MM).astype(float)
    out["dry_days_15d"] = _grouped_rolling(is_dry, blocks, 15, "sum")

    # --- climatological anomaly ---------------------------------------------
    rain_15d = _grouped_rolling(frame[COL_RAIN], blocks, 15, "sum")
    climo = pentad_climatology(frame, training_seasons=training_seasons)
    keyed = frame[[COL_BLOCK, COL_DATE]].copy()
    keyed["pentad"] = ((keyed[COL_DATE].dt.dayofyear - 1) // 5).astype(int)
    keyed = keyed.merge(climo, on=[COL_BLOCK, "pentad"], how="left")
    # 15 days spans three pentads, so scale the pentad mean up to the window.
    expected = keyed["pentad_rain_mean"].to_numpy() * 15.0
    spread = keyed["pentad_rain_std"].to_numpy() * np.sqrt(15.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["rain_anomaly_15d"] = (rain_15d.to_numpy() - expected) / np.where(
            spread > 0, spread, np.nan
        )

    # --- seasonal phase ------------------------------------------------------
    season_start = pd.to_datetime(
        {
            "year": frame[COL_DATE].dt.year,
            "month": MONSOON_START_MONTH,
            "day": MONSOON_START_DAY,
        }
    )
    day_of_season = (frame[COL_DATE] - season_start).dt.days
    phase = 2.0 * np.pi * day_of_season / SEASON_LENGTH_DAYS
    out["day_of_season_sin"] = np.sin(phase)
    out["day_of_season_cos"] = np.cos(phase)

    # --- ensemble forecast ---------------------------------------------------
    out["ens_dry_fraction"] = frame[COL_ENS_DRY_FRACTION]

    # --- teleconnections -----------------------------------------------------
    out["oni_lag30"] = 0.0
    out["mjo_amplitude_lag10"] = 0.0
    if teleconnections is not None:
        merged = frame[[COL_DATE]].merge(teleconnections, on=COL_DATE, how="left")
        if "oni" in merged.columns:
            out["oni_lag30"] = _grouped_shift(
                pd.Series(merged["oni"].to_numpy(), index=frame.index), blocks, 30
            )
        if "mjo_amplitude" in merged.columns:
            out["mjo_amplitude_lag10"] = _grouped_shift(
                pd.Series(merged["mjo_amplitude"].to_numpy(), index=frame.index), blocks, 10
            )

    return out[list(FEATURE_NAMES)]
