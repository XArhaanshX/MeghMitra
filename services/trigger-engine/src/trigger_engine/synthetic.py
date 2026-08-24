"""Synthetic monsoon weather, for tests and the pipeline smoke run.

THIS IS NOT REAL DATA AND MUST NEVER BE PRESENTED AS A RESULT.

It exists for one reason: `AGENTS.md` requires `make test` to run with no live
Postgres and no network, and the real inputs (IMD gridded rainfall, ECMWF open
ensembles, ERA5-Land) are all network-fetched and licence-tagged. Without a
synthetic generator the entire ML pipeline would be untestable in CI -- and for a
pipeline whose failure modes are silent (leakage, misalignment, a mis-signed
constraint) that is not an acceptable trade.

Any skill score computed on this data measures whether the *code* works, not
whether the *method* works. `pipeline.run_demo` prints that caveat alongside its
results, and it should stay printed until real adapters land.

WHY A RICHARDSON-TYPE CHAIN RATHER THAN NOISE

Gaussian noise would exercise the code paths but produce a panel where dry spells
have no persistence -- and persistence is the entire structure the model is meant
to find. The standard stochastic weather generator design captures what matters
with two components:

  occurrence  a two-state Markov chain over wet/dry. Transition probabilities
              P(wet|wet) and P(wet|dry) are what create realistic runs of dry
              days: the dry spells themselves.
  intensity   a gamma distribution on wet days. Daily rainfall is strongly
              right-skewed with a long tail, which gamma reproduces and a normal
              does not.

Seasonal modulation is layered on top so July is wetter than June, giving the
climatology baseline real structure to learn.

THE SYNTHETIC ENSEMBLE IS DELIBERATELY MISCALIBRATED

`_synthesise_ensemble` produces a forecast with genuine skill that is also
over-confident -- probabilities pushed toward 0 and 1 relative to truth. That is
what operational ensembles actually do (they are typically under-dispersive), and
it means calibration has something real to correct. An ensemble synthesised as
perfectly calibrated would make post-processing look pointless for reasons that
are purely an artifact of the generator.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trigger_engine.config import (
    COL_BLOCK,
    COL_DATE,
    COL_ENS_DRY_FRACTION,
    COL_RAIN,
    COL_TMAX,
    COL_TMIN,
    DRY_SPELL_MIN_DAYS,
    RAINY_DAY_THRESHOLD_MM,
    RANDOM_SEED,
)

SIRSA_BLOCKS: tuple[str, ...] = (
    "Sirsa",
    "Ellenabad",
    "Rania",
    "Dabwali",
    "Odhan",
    "Baragudha",
    "Nathusari Chopta",
)
"""Block labels only. No real data about these places is encoded here."""


def _seasonal_wetness(day_of_season: np.ndarray) -> np.ndarray:
    """Seasonal envelope: a smooth peak in mid-to-late July.

    Gives the climatology baseline genuine seasonal structure to learn, so it is a
    real opponent rather than a flat rate any model beats trivially.
    """
    return 0.35 + 0.45 * np.sin(np.pi * np.clip(day_of_season, 0, 122) / 122.0)


def _synthesise_ensemble(panel: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Attach an ensemble dry-spell fraction with real but imperfect skill.

    Built by peeking at the future dry-run length -- legitimate *here* only because
    this stands in for a forecast system that genuinely has skill. The peek is then
    degraded twice:

      1. additive noise, so the forecast is wrong often enough to be realistic;
      2. a sharpening transform, pushing probabilities toward 0 and 1 so the
         result is over-confident.

    Step 2 is the important one. It reproduces the under-dispersion of real
    ensembles and gives the ELR calibrator and `IsotonicRecalibrator` something
    genuine to fix. Without it, post-processing would appear worthless for reasons
    entirely internal to this generator.
    """
    is_dry = (panel[COL_RAIN] < RAINY_DAY_THRESHOLD_MM).astype(float)
    blocks = panel[COL_BLOCK]

    future_dry = (
        is_dry[::-1]
        .groupby(blocks[::-1], sort=False)
        .rolling(14, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)[::-1]
    )

    truth_signal = (future_dry >= (DRY_SPELL_MIN_DAYS / 14.0)).astype(float).to_numpy()
    noisy = truth_signal * 0.55 + rng.random(len(panel)) * 0.45
    sharpened = np.clip(0.5 + 1.5 * (noisy - 0.5), 0.02, 0.98)

    panel = panel.copy()
    panel[COL_ENS_DRY_FRACTION] = sharpened
    return panel


def generate_panel(
    *,
    seasons: range = range(1990, 2026),
    blocks: tuple[str, ...] = SIRSA_BLOCKS,
    seed: int = RANDOM_SEED,
    missing_rain_fraction: float = 0.01,
) -> pd.DataFrame:
    """Generate a synthetic block-day observation panel.

    Args:
        seasons: Calendar years to generate. The default spans 36 seasons, close
            to what the real IMD gridded record would supply.
        blocks: Block labels.
        seed: Fixed for reproducibility, as in the load-forecasting benchmark.
        missing_rain_fraction: Share of days with rainfall set to NaN, so the
            preprocessing gap-handling path is exercised on every test run rather
            than only when real data happens to be broken.

    Returns:
        A long frame with `REQUIRED_OBSERVATION_COLUMNS` plus
        `COL_ENS_DRY_FRACTION`, covering May 1 - September 30 of each season (May
        supplies the water-balance spin-up).

    Vectorized except for the Markov chain, which is sequential by nature and loops
    over days while updating all blocks at once -- the same pattern as
    `waterbalance.run_water_balance`.
    """
    rng = np.random.default_rng(seed)
    frames = []

    for season in seasons:
        dates = pd.date_range(f"{season}-05-01", f"{season}-09-30", freq="D")
        n_days, n_blocks = len(dates), len(blocks)
        day_of_season = (dates - pd.Timestamp(f"{season}-06-01")).days.to_numpy()

        # Season-level wet/dry bias, standing in for ENSO/IOD modulation: some
        # monsoons are simply drier than others, and that year-to-year variance is
        # what makes leave-one-season-out cross-validation meaningful.
        season_factor = rng.normal(1.0, 0.18)
        wet_probability = np.clip(_seasonal_wetness(day_of_season) * season_factor, 0.05, 0.95)

        # Two-state Markov chain. The persistence parameters are what generate dry
        # spells of realistic length; independent draws would not.
        is_wet = np.zeros((n_days, n_blocks), dtype=bool)
        state = rng.random(n_blocks) < wet_probability[0]
        for day in range(n_days):
            p_base = wet_probability[day]
            # P(wet|wet) > P(wet|dry): rainfall clusters into active spells.
            p_transition = np.where(state, 0.35 + 0.5 * p_base, 0.55 * p_base)
            # Blocks in one district share synoptic weather. A common shock plus a
            # small per-block deviation reproduces that correlation -- which is
            # exactly why blocks are not independent samples, the point
            # `evaluation.block_bootstrap_ci` exists to respect.
            draw = 0.75 * rng.random() + 0.25 * rng.random(n_blocks)
            state = draw < p_transition
            is_wet[day] = state

        # Gamma intensity on wet days: right-skewed with a long tail, unlike a
        # normal. Zero on dry days.
        intensity = rng.gamma(shape=0.9, scale=11.0, size=(n_days, n_blocks))
        rain = np.where(is_wet, intensity, 0.0)

        # Temperature: seasonal mean, cooler with a compressed diurnal range on wet
        # days. The compression matters because Hargreaves ET0 reads diurnal range
        # as a cloudiness proxy.
        base_temp = 34.0 - 4.0 * np.sin(np.pi * np.clip(day_of_season, 0, 122) / 122.0)
        tmax = base_temp[:, None] + rng.normal(0, 1.6, (n_days, n_blocks)) - 3.5 * is_wet
        tmin = tmax - (11.0 - 4.0 * is_wet) + rng.normal(0, 0.8, (n_days, n_blocks))

        frames.append(
            pd.DataFrame(
                {
                    COL_BLOCK: np.repeat(blocks, n_days),
                    COL_DATE: np.tile(dates, n_blocks),
                    COL_RAIN: rain.T.ravel(),
                    COL_TMAX: tmax.T.ravel(),
                    COL_TMIN: tmin.T.ravel(),
                }
            )
        )

    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values([COL_BLOCK, COL_DATE]).reset_index(drop=True)
    panel = _synthesise_ensemble(panel, rng)

    if missing_rain_fraction > 0:
        gaps = rng.random(len(panel)) < missing_rain_fraction
        panel.loc[gaps, COL_RAIN] = np.nan

    return panel


def generate_teleconnections(
    seasons: range = range(1990, 2026), seed: int = RANDOM_SEED
) -> pd.DataFrame:
    """Synthetic ONI and MJO amplitude series, daily.

    Both are red-noise-like in reality -- slowly varying and autocorrelated -- so an
    AR(1) process is a reasonable stand-in. It carries no real teleconnection
    signal, so the model correctly finds these columns uninformative here. Real ONI
    comes from NOAA CPC and real MJO amplitude from the Wheeler-Hendon RMM index;
    both are open, and both are ingest-adapter work.
    """
    rng = np.random.default_rng(seed + 1)
    dates = pd.date_range(f"{min(seasons)}-01-01", f"{max(seasons)}-12-31", freq="D")

    def ar1(phi: float, sigma: float) -> np.ndarray:
        """AR(1) walk. `phi` near 1 gives the long memory these indices have."""
        innovations = rng.normal(0, sigma, len(dates))
        out = np.zeros(len(dates))
        for i in range(1, len(dates)):
            out[i] = phi * out[i - 1] + innovations[i]
        return out

    return pd.DataFrame(
        {
            COL_DATE: dates,
            # phi near 1: ENSO evolves over months, not days.
            "oni": ar1(0.995, 0.08),
            "mjo_amplitude": np.abs(ar1(0.97, 0.15)),
        }
    )
