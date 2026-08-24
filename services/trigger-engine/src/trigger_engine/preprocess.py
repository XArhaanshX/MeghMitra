"""Raw block-day observations -> a regular, gap-explicit panel.

This is the load-forecasting preprocessing template retargeted from 15-minute
electricity demand to daily block rainfall. Three of its steps carry over
unchanged, and three must be inverted -- getting that distinction right is the
whole job of this module, so each is spelled out at its call site.

Carried over:
  * chronological sort and de-duplication, keeping the first occurrence
  * an enforced regular frequency with explicit NaN at missing timestamps
    (`asfreq`-equivalent), so a gap is visible rather than silently closed
  * every downstream transform reading from t-1 rather than t (see features.py)

Inverted, because rainfall is not electricity demand:
  * 4-sigma winsorization -> physical plausibility cap only
  * blanket forward-fill -> per-variable imputation policy
  * "missing means carry the last value" -> for rain, missing means *unknown*,
    and the row is flagged so labels can drop it

Performance: everything here is vectorized pandas over the whole panel. There
are no per-row Python loops and no `groupby.apply` with a Python callable, both
of which dominate runtime on panels of this shape.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trigger_engine.config import (
    COL_BLOCK,
    COL_DATE,
    COL_ENS_DRY_FRACTION,
    COL_RAIN,
    COL_RAIN_IMPUTED,
    COL_TMAX,
    COL_TMIN,
    MONSOON_END_DAY,
    MONSOON_END_MONTH,
    MONSOON_START_DAY,
    MONSOON_START_MONTH,
    PHYSICAL_MAX_DAILY_RAIN_MM,
    REQUIRED_OBSERVATION_COLUMNS,
    TEMPERATURE_INTERPOLATE_LIMIT_DAYS,
    WATER_BALANCE_SPINUP_DAYS,
)


class PanelSchemaError(ValueError):
    """Raised when the input frame is missing a column the pipeline requires.

    A loud failure here is deliberate. A silently-absent rainfall column would
    propagate as all-NaN through the water balance and surface as a
    uniformly-dry season, which looks like a plausible drought rather than a
    bug.
    """


@dataclass(frozen=True, slots=True)
class PreprocessReport:
    """What preprocessing actually did, for the audit trail.

    Returned alongside the panel rather than logged, because these counts decide
    whether a season's verification numbers are trustworthy: a season that was
    40% imputed should not contribute to a headline skill score without that
    being visible.
    """

    rows_in: int
    rows_out: int
    duplicate_rows_dropped: int
    missing_rain_days: int
    implausible_rain_values: int
    blocks: int
    seasons: tuple[int, ...]

    @property
    def imputed_fraction(self) -> float:
        """Share of panel rows with no observed rainfall. The headline caveat."""
        return self.missing_rain_days / self.rows_out if self.rows_out else 0.0


def season_of(dates: pd.Series) -> pd.Series:
    """Map each date to the monsoon season (calendar year) it belongs to.

    Trivial for JJAS, which never crosses a year boundary, but kept as a named
    function because the season -- not the calendar year -- is the unit that
    cross-validation groups on (`splits.py`), and naming it makes that grouping
    self-documenting at every call site.
    """
    return dates.dt.year


def in_monsoon_window(dates: pd.Series, *, include_spinup: bool = False) -> pd.Series:
    """Boolean mask for dates inside the JJAS season.

    With `include_spinup`, the window opens `WATER_BALANCE_SPINUP_DAYS` earlier
    so the soil-water bucket can reach a physically-realistic state before the
    first day we score. Without spin-up, June's soil moisture is an artifact of
    whatever the bucket was initialised to, and a model will happily learn that
    artifact as a seasonal signal.
    """
    start_doy = pd.Timestamp(2001, MONSOON_START_MONTH, MONSOON_START_DAY).day_of_year
    end_doy = pd.Timestamp(2001, MONSOON_END_MONTH, MONSOON_END_DAY).day_of_year
    if include_spinup:
        start_doy -= WATER_BALANCE_SPINUP_DAYS

    # day_of_year shifts by one in leap years after February. The monsoon window
    # sits entirely after February, so subtract the leap offset to compare every
    # year on the same non-leap ordinal scale.
    doy = dates.dt.dayofyear - (dates.dt.is_leap_year & (dates.dt.month > 2)).astype(int)
    return (doy >= start_doy) & (doy <= end_doy)


def _validate_columns(frame: pd.DataFrame) -> None:
    """Fail fast and by name if the caller's frame is not the agreed panel shape."""
    missing = [c for c in REQUIRED_OBSERVATION_COLUMNS if c not in frame.columns]
    if missing:
        raise PanelSchemaError(
            f"observation frame is missing required column(s): {', '.join(missing)}. "
            f"Expected at least {list(REQUIRED_OBSERVATION_COLUMNS)}."
        )


def _regular_daily_index(frame: pd.DataFrame) -> pd.DataFrame:
    """Reindex every block onto a gap-free daily date range.

    Equivalent to the load pipeline's `asfreq('15min')` step: a missing day must
    become a row with NaN, not an absent row. If gaps stay absent, a rolling
    7-day window silently spans 9 calendar days and every lag is wrong by an
    amount that varies with the gap -- the kind of error that never raises and
    quietly inflates skill.

    Built with a MultiIndex product rather than a per-block loop so the cost is
    one reindex regardless of block count.
    """
    blocks = frame[COL_BLOCK].unique()
    full_range = pd.date_range(frame[COL_DATE].min(), frame[COL_DATE].max(), freq="D")
    full_index = pd.MultiIndex.from_product([blocks, full_range], names=[COL_BLOCK, COL_DATE])

    return (
        frame.set_index([COL_BLOCK, COL_DATE])
        .reindex(full_index)
        .reset_index()
        .sort_values([COL_BLOCK, COL_DATE], kind="stable")
        .reset_index(drop=True)
    )


def _cap_implausible_rain(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Void physically impossible rainfall, rather than clipping the distribution.

    The load pipeline winsorized at mu +/- 4 sigma. That is correct for demand,
    which is near-Gaussian around a diurnal cycle, and wrong here: daily rainfall
    is zero-inflated and right-skewed, so mu + 4 sigma falls *inside* the range
    of genuine monsoon bursts. Clipping there deletes precisely the revival
    events the trigger engine exists to detect.

    So values above `PHYSICAL_MAX_DAILY_RAIN_MM` are treated as instrument or
    unit errors and set to NaN (to be handled by the imputation policy), while
    every plausible extreme is left exactly as observed. Negative rainfall is
    likewise voided rather than clamped to zero -- a negative reading means the
    sensor or the parse is broken, and pretending it was a dry day would bias
    the dry-spell target.
    """
    rain = frame[COL_RAIN]
    implausible = (rain < 0) | (rain > PHYSICAL_MAX_DAILY_RAIN_MM)
    count = int(implausible.sum())
    if count:
        frame = frame.copy()
        frame.loc[implausible, COL_RAIN] = np.nan
    return frame, count


def _impute_per_variable(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply a different missing-value policy to each variable, on purpose.

    The load pipeline used one policy (short forward-fill, then interpolate) for
    one variable. Applying that here would be actively harmful for two of the
    three:

    rainfall -- no imputation at all. Forward-filling carries yesterday's 40 mm
        into today and invents a rain event; zero-filling invents a dry day and
        biases the dry-spell label directly, in the direction that makes the
        model look better than it is. Missing stays NaN and the row is flagged
        via `COL_RAIN_IMPUTED` so `labels.py` can drop any target window that
        depends on it. Spatial infill from neighbouring grid cells is the right
        fix and belongs in the ingest adapter, where neighbour geometry is known.

    temperature -- short linear interpolation. Temperature is smooth and
        strongly autocorrelated day to day, so a 1-3 day bridge is low-risk, and
        it only feeds ET0, where small errors are damped by the soil bucket.

    ensemble dry-fraction -- no imputation. A missing forecast cycle is a reason
        to abstain, not to guess. Leaving it NaN means the model declines to
        score that day, which is the correct behaviour for a system whose
        default output is silence.

    Interpolation is applied per block via `groupby().transform()`, which stays
    in pandas' C paths -- unlike `groupby().apply()` with a Python function,
    which is orders of magnitude slower on a panel of this shape.
    """
    frame = frame.copy()
    frame[COL_RAIN_IMPUTED] = frame[COL_RAIN].isna()

    grouped = frame.groupby(COL_BLOCK, sort=False)
    for column in (COL_TMIN, COL_TMAX):
        if column in frame.columns:
            frame[column] = grouped[column].transform(
                lambda s: s.interpolate(
                    method="linear",
                    limit=TEMPERATURE_INTERPOLATE_LIMIT_DAYS,
                    limit_direction="both",
                )
            )
    return frame


def preprocess_observations(
    observations: pd.DataFrame,
    *,
    include_spinup: bool = True,
) -> tuple[pd.DataFrame, PreprocessReport]:
    """Turn raw block-day observations into the canonical panel.

    Args:
        observations: One row per block per day. Must carry at least
            `REQUIRED_OBSERVATION_COLUMNS`; `COL_ENS_DRY_FRACTION` is optional
            and passes through untouched when present.
        include_spinup: Keep the pre-season days the water balance needs to warm
            up. Set False only when the caller has already run the water balance
            and wants the scoring window alone.

    Returns:
        `(panel, report)`. The panel is sorted by (block, date), has a gap-free
        daily index within its date span, carries `COL_RAIN_IMPUTED`, and is
        restricted to the monsoon window.

    Order matters and is not arbitrary:
      1. validate  -- fail by name before any work
      2. sort + dedup -- so "first occurrence wins" is well-defined
      3. reindex   -- create the missing rows before anything looks for them
      4. cap       -- void implausible values so imputation sees them as missing
      5. impute    -- per-variable policy, flags recorded
      6. window    -- trim last, so interpolation could use data either side of
                      the season boundary rather than being truncated by it
    """
    _validate_columns(observations)
    rows_in = len(observations)

    frame = observations.copy()
    frame[COL_DATE] = pd.to_datetime(frame[COL_DATE])

    frame = frame.sort_values([COL_BLOCK, COL_DATE], kind="stable")
    before_dedup = len(frame)
    frame = frame.drop_duplicates(subset=[COL_BLOCK, COL_DATE], keep="first")
    duplicates_dropped = before_dedup - len(frame)

    frame = _regular_daily_index(frame)
    frame, implausible = _cap_implausible_rain(frame)
    frame = _impute_per_variable(frame)

    frame = frame.loc[in_monsoon_window(frame[COL_DATE], include_spinup=include_spinup)]
    frame = frame.reset_index(drop=True)

    if COL_ENS_DRY_FRACTION not in frame.columns:
        frame[COL_ENS_DRY_FRACTION] = np.nan

    report = PreprocessReport(
        rows_in=rows_in,
        rows_out=len(frame),
        duplicate_rows_dropped=duplicates_dropped,
        missing_rain_days=int(frame[COL_RAIN_IMPUTED].sum()),
        implausible_rain_values=implausible,
        blocks=int(frame[COL_BLOCK].nunique()),
        seasons=tuple(sorted(season_of(frame[COL_DATE]).unique().tolist())),
    )
    return frame, report
