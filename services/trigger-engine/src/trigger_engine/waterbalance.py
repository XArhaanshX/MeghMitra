"""FAO-56 root-zone water balance: rainfall and temperature -> soil moisture state.

This module contains no machine learning. It is a physical simulator, and saying
so plainly is a strength rather than an omission: it is the physics that lets a
~12-feature logistic regression work on roughly 40 seasons of record. Handing the
model a *soil moisture deficit* instead of thirty raw lagged rainfall columns
removes most of what it would otherwise have to learn from data it does not have.

Why a single-layer bucket rather than something richer:

  * FAO-56 (Allen et al., FAO Irrigation & Drainage Paper 56) is the standard
    reference for agricultural water balance, and its single crop-coefficient
    form is the variant that runs on the inputs we actually have per block.
  * The dual-Kc form splits evaporation and transpiration and needs wet-surface
    fraction and per-stage rooting depth we do not have at block scale.
  * A physically-calibrated Richards-equation solver needs soil hydraulic
    parameters that do not exist at 3,196-block resolution for India.

A wrong complicated model is worse than an honest simple one, and the downstream
consumer only needs an ordinal signal ("is the profile drying out?"), not a
centimetre-accurate water table.

Why Hargreaves-Samani for ET0 rather than FAO-56 Penman-Monteith: Penman-Monteith
is the FAO-56 primary method but requires humidity, wind speed and radiation.
Block-scale gridded products reliably carry only Tmin/Tmax. Hargreaves-Samani is
FAO-56's own documented fallback for exactly that situation. When richer forcing
data lands, `reference_et0` is the one function to swap.

PERFORMANCE NOTE. The bucket update is a recursion -- S_t depends on S_{t-1}
through a clamp -- so it cannot be expressed as a cumulative sum. Rather than
loop over rows, this module pivots to a (days x blocks) matrix and loops over
*days*, updating every block at once with numpy. For a season of ~150 days that
is ~150 vectorized steps regardless of how many blocks are in the panel, which
keeps a full multi-decade run in the low hundreds of milliseconds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trigger_engine.config import (
    COL_BLOCK,
    COL_DATE,
    COL_RAIN,
    COL_TMAX,
    COL_TMIN,
    DEFAULT_AWC_MM,
    HARGREAVES_COEFFICIENT,
    RAINY_DAY_THRESHOLD_MM,
    RUNOFF_FRACTION,
)

_RA_MM_COEFFICIENT = 15.34
"""(24*60/pi) * Gsc / lambda, with Gsc = 0.0820 MJ m-2 min-1 and lambda = 2.45
MJ kg-1. Folds FAO-56's radiation constant and the MJ->mm conversion into one
number so `extraterrestrial_radiation` returns mm/day directly."""


def extraterrestrial_radiation(latitude_deg: float, day_of_year: np.ndarray) -> np.ndarray:
    """Top-of-atmosphere radiation Ra, in mm/day of equivalent evaporation.

        Ra = 15.34 * dr * [w*sin(phi)*sin(d) + cos(phi)*cos(d)*sin(w)]

    Standard astronomical geometry (FAO-56 Ch. 3). Ra depends only on latitude
    and day of year, so it is fully determined without any observation -- which
    is what makes temperature-only ET0 possible at all. The seasonal energy cycle
    comes from geometry; temperature supplies the day-to-day departure.

    Args:
        latitude_deg: Block centroid latitude, degrees north.
        day_of_year: 1-366. Any shape; broadcasting is the caller's choice.

    Returns:
        Ra for each day, same shape as `day_of_year`.
    """
    phi = np.deg2rad(latitude_deg)
    # Inverse relative Earth-Sun distance, and solar declination in radians.
    dr = 1.0 + 0.033 * np.cos(2.0 * np.pi * day_of_year / 365.0)
    declination = 0.409 * np.sin(2.0 * np.pi * day_of_year / 365.0 - 1.39)

    # Sunset hour angle. The clip guards |tan(phi)tan(d)| > 1, which has no real
    # arccos; unreachable at Indian latitudes but it keeps the function total
    # rather than NaN-producing if this is ever reused further north.
    omega = np.arccos(np.clip(-np.tan(phi) * np.tan(declination), -1.0, 1.0))

    return (
        _RA_MM_COEFFICIENT
        * dr
        * (
            omega * np.sin(phi) * np.sin(declination)
            + np.cos(phi) * np.cos(declination) * np.sin(omega)
        )
    )


def reference_et0(
    tmin_c: np.ndarray,
    tmax_c: np.ndarray,
    latitude_deg: float,
    day_of_year: np.ndarray,
) -> np.ndarray:
    """Reference evapotranspiration ET0 by Hargreaves-Samani, mm/day.

        ET0 = 0.0023 * Ra * (Tmean + 17.8) * sqrt(Tmax - Tmin)

    The `sqrt(Tmax - Tmin)` term is a proxy for cloudiness: a wide diurnal range
    means clear skies and a high radiation load, a narrow one means overcast and
    likely humid. That is precisely why this equation degrades least during the
    monsoon, when the diurnal range genuinely does collapse on rainy days.

    Returns ET0 clipped at zero. The equation can go negative for physically
    impossible inputs (Tmean below -17.8 C), which cannot occur in Haryana, but
    it should not silently produce negative water demand if it did.
    """
    tmean = (tmin_c + tmax_c) / 2.0
    # Guard the sqrt: Tmax < Tmin means the inputs are swapped or corrupt.
    diurnal_range = np.clip(tmax_c - tmin_c, 0.0, None)
    ra = extraterrestrial_radiation(latitude_deg, day_of_year)
    et0 = HARGREAVES_COEFFICIENT * ra * (tmean + 17.8) * np.sqrt(diurnal_range)
    return np.clip(et0, 0.0, None)


def _pivot_to_matrix(panel: pd.DataFrame, column: str) -> pd.DataFrame:
    """Reshape long panel -> (date x block) matrix so the day loop is vectorized."""
    return panel.pivot(index=COL_DATE, columns=COL_BLOCK, values=column).sort_index()


def run_water_balance(
    panel: pd.DataFrame,
    *,
    latitude_deg: float = 29.5,
    awc_mm: float = DEFAULT_AWC_MM,
    crop_coefficient: float = 1.0,
    runoff_fraction: float = RUNOFF_FRACTION,
    initial_fraction: float = 0.5,
) -> pd.DataFrame:
    """Simulate the daily root-zone bucket for every block in the panel.

    The model, per block per day:

        P_eff = P * (1 - runoff_fraction)      effective rainfall reaching soil
        ET_c  = Kc * ET0                       crop water demand
        S_t   = clip(S_{t-1} + P_eff - ET_c, 0, AWC)

    Clipping at 0 and AWC is what makes this a *bucket*: water beyond capacity
    drains away rather than accumulating into an unphysical reservoir, and the
    profile cannot go below empty. Both bounds matter for the signal we want --
    saturation means extra rain stops mattering, and an empty profile is exactly
    the stressed state the DACP conditions describe.

    Args:
        panel: Output of `preprocess.preprocess_observations`, including the
            pre-season spin-up days.
        latitude_deg: Block centroid latitude. One value serves all blocks here
            because a single district spans well under a degree; this becomes a
            per-block column once the real GIS join lands.
        awc_mm: Total available water in the root zone. **Fit parameter** -- must
            be estimated on training seasons only once soil data is joined, or it
            leaks test-season information into every downstream feature.
        crop_coefficient: FAO-56 single Kc. 1.0 is a neutral reference-crop
            default; a per-crop, per-stage curve replaces it when the crop
            calendar is wired.
        runoff_fraction: Share of rainfall lost before infiltration.
        initial_fraction: Starting fill as a fraction of AWC. Its influence is
            deliberately erased by the spin-up window before the scored season
            begins.

    Returns:
        The panel with `soil_moisture_mm`, `soil_moisture_fraction`, `et0_mm`,
        `is_dry_day` and `consecutive_dry_days` added.

    Missing rainfall (NaN, from `preprocess`) is treated as zero infiltration
    *inside the simulation only* -- there is no defensible alternative when
    stepping a recursion -- but those rows keep their `rain_is_imputed` flag so
    labels can drop any target window depending on them. The distinction matters:
    the simulator has to put a number somewhere, the label does not have to trust
    it.
    """
    rain = _pivot_to_matrix(panel, COL_RAIN)
    tmin = _pivot_to_matrix(panel, COL_TMIN)
    tmax = _pivot_to_matrix(panel, COL_TMAX)

    dates = rain.index
    day_of_year = dates.dayofyear.to_numpy()

    # ET0 for every (day, block) in one vectorized call. day_of_year is given a
    # trailing axis so it broadcasts across block columns.
    et0_matrix = reference_et0(
        tmin.to_numpy(dtype=float),
        tmax.to_numpy(dtype=float),
        latitude_deg,
        day_of_year[:, None],
    )
    et_crop = crop_coefficient * et0_matrix

    rain_values = np.nan_to_num(rain.to_numpy(dtype=float), nan=0.0)
    effective_rain = rain_values * (1.0 - runoff_fraction)

    n_days, n_blocks = rain_values.shape
    storage = np.empty((n_days, n_blocks), dtype=float)
    current = np.full(n_blocks, initial_fraction * awc_mm, dtype=float)

    # The only loop in the pipeline. It runs over days, not rows: each iteration
    # advances every block at once, so cost scales with season length (~150)
    # rather than with panel size.
    for day in range(n_days):
        demand = np.nan_to_num(et_crop[day], nan=0.0)
        current = np.clip(current + effective_rain[day] - demand, 0.0, awc_mm)
        storage[day] = current

    storage_long = (
        pd.DataFrame(storage, index=dates, columns=rain.columns)
        .stack()
        .rename("soil_moisture_mm")
        .reset_index()
    )
    et0_long = (
        pd.DataFrame(et0_matrix, index=dates, columns=rain.columns)
        .stack()
        .rename("et0_mm")
        .reset_index()
    )

    result = panel.merge(storage_long, on=[COL_DATE, COL_BLOCK], how="left").merge(
        et0_long, on=[COL_DATE, COL_BLOCK], how="left"
    )

    result["soil_moisture_fraction"] = (result["soil_moisture_mm"] / awc_mm).clip(0.0, 1.0)
    result["is_dry_day"] = result[COL_RAIN] < RAINY_DAY_THRESHOLD_MM
    result["consecutive_dry_days"] = consecutive_dry_days(result)
    return result


def consecutive_dry_days(frame: pd.DataFrame) -> pd.Series:
    """Length of the dry run ending at each row, counted per block.

    Vectorized as a "reset-on-wet" cumulative count rather than a Python loop:

      1. `cumsum` of the dry flag gives a monotonically rising counter;
      2. subtracting that counter's value as of the most recent *wet* day resets
         it to zero at every wet day.

    A NaN rainfall day is **not** counted as dry. Counting it as dry would extend
    a spell using a day nobody observed -- letting a data gap manufacture a
    drought, which is the exact failure the per-variable imputation policy exists
    to prevent.
    """
    is_dry = (frame[COL_RAIN] < RAINY_DAY_THRESHOLD_MM).fillna(False)
    blocks = frame[COL_BLOCK]
    running = is_dry.groupby(blocks, sort=False).cumsum()
    reset_points = running.where(~is_dry).groupby(blocks, sort=False).ffill().fillna(0)
    return (running - reset_points).astype(int)
