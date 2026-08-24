"""Constants for the trigger engine, each with the reason it holds that value.

Numbers in a weather pipeline are load-bearing: 2.5 mm is not a tunable, it is
the definition India's meteorological service uses, and the whole point of Ankur
is to speak the government's vocabulary rather than invent one. Anything here
that came from a paper or an operational definition says so. Anything that is a
project choice is labelled a project choice, so a reviewer can tell the two
apart.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Rainfall thresholds
# ---------------------------------------------------------------------------

RAINY_DAY_THRESHOLD_MM: Final[float] = 2.5
"""A day with < 2.5 mm is a dry day.

This is IMD's operational definition of a rainy day (>= 2.5 mm in 24 hours), not
a threshold we picked. Using anything else would mean our "dry spell" and the
DACP's "dry spell" are different events, and the citation would be misleading
even when the extraction was perfect."""

DRY_SPELL_MIN_DAYS: Final[int] = 5
"""Minimum run of dry days that counts as a spell for the *model target*.

Project choice, and a deliberate mismatch with the DACP's own 15-20 day language.
Reason: a 15-20 day spell is roughly an order of magnitude rarer than a 5-day
one, and at ~40 seasons of record the 15-20 day label leaves too few positives to
calibrate against. We train on the frequent event and map upward at the condition
layer (`conditions.py`), rather than training directly on a label we cannot
verify. `labels.py` can build either -- `evaluation.py` reports base rates for
both so the trade is visible rather than assumed."""

PHYSICAL_MAX_DAILY_RAIN_MM: Final[float] = 1000.0
"""Reject-above value for observed daily rainfall.

Note this is a *plausibility cap*, not winsorization. Our load-forecasting work
clipped at mu +/- 4 sigma, which is right for electricity demand (near-Gaussian
around a diurnal cycle) and wrong for rainfall: daily rain is zero-inflated and
heavy-tailed, so mu + 4 sigma sits inside the range of real monsoon bursts.
Clipping there would delete the events the system exists to detect. India's
24-hour record is roughly 990 mm, so a value above this is an instrument or
units error, not weather."""

# ---------------------------------------------------------------------------
# Season window
# ---------------------------------------------------------------------------

MONSOON_START_MONTH: Final[int] = 6
MONSOON_START_DAY: Final[int] = 1
MONSOON_END_MONTH: Final[int] = 9
MONSOON_END_DAY: Final[int] = 30
"""June 1 - September 30, the standard Indian southwest monsoon season (JJAS).

Restricting the panel to JJAS is what keeps the class balance workable: outside
the season nearly every day is dry, so including them would swamp the positive
class with trivially-predictable examples and inflate every skill score."""

WATER_BALANCE_SPINUP_DAYS: Final[int] = 30
"""Pre-season days simulated before June 1 so the soil bucket starts from a
physically-reached state rather than an arbitrary one.

Without spin-up, the first ~2 weeks of every season carry an initialisation
artifact that the model would happily learn as a seasonal signal."""

# ---------------------------------------------------------------------------
# Forecast leads
# ---------------------------------------------------------------------------

FORECAST_LEAD_DAYS: Final[tuple[int, ...]] = (7, 14, 21, 30)
"""Lead windows we predict over, matching SIH26086's "7-to-30-day outlook".

One model per lead rather than a multi-output head: at this sample size a shared
head mostly shares noise, and separate models let each lead's calibration be
inspected independently -- which matters because reliability degrades with lead
and we want to see exactly where it stops being usable."""

# ---------------------------------------------------------------------------
# Imputation limits -- deliberately per-variable
# ---------------------------------------------------------------------------

SOIL_MOISTURE_FFILL_LIMIT_DAYS: Final[int] = 2
"""Soil moisture is a state variable with real physical inertia, so carrying the
last value forward for a day or two approximates reality. This is the one place
the load-forecasting pipeline's forward-fill rule transfers directly."""

TEMPERATURE_INTERPOLATE_LIMIT_DAYS: Final[int] = 3
"""Temperature is smooth and strongly autocorrelated; short linear interpolation
is low-risk."""

# Rainfall gets no entry here on purpose. Forward-filling rain invents a rain
# event; zero-filling invents a dry day and biases the dry-spell target directly.
# `preprocess.py` masks missing rain and flags it instead. See that module.

# ---------------------------------------------------------------------------
# Water balance (FAO-56)
# ---------------------------------------------------------------------------

DEFAULT_AWC_MM: Final[float] = 150.0
"""Total available water in the root zone, mm.

Placeholder for a real per-block soil join (NBSS&LUP / SoilGrids). 150 mm is a
reasonable mid-range value for a medium-textured profile at ~1 m rooting depth
under FAO-56. Marked as a fit parameter in `waterbalance.py`, and it must be
fitted on training years only once real soil data lands."""

RUNOFF_FRACTION: Final[float] = 0.15
"""Fraction of daily rainfall lost to runoff before it reaches the root zone.

A single-parameter stand-in for the SCS curve-number method. Chosen over full
curve-number accounting because CN requires land-use and antecedent-moisture
classes we do not have per block, and a wrong CN is worse than an honest constant."""

HARGREAVES_COEFFICIENT: Final[float] = 0.0023
"""The 0.0023 in Hargreaves-Samani ET0. From the published form of the equation,
not tuned by us."""

# ---------------------------------------------------------------------------
# Condition detection thresholds (project choices, tuned to the DACP's language)
# ---------------------------------------------------------------------------

DELAYED_ONSET_DAYS: Final[int] = 21
"""'Delayed onset of monsoon by more than 3 weeks' -- read straight off the
Sirsa plan's own wording."""

SOWING_WINDOW_DAYS: Final[int] = 30
"""Days after sowing during which a dry spell counts as the 'after sowing' case
rather than a mid-season break. Bounds the window in which re-sowing is still
agronomically possible."""

DRY_SPELL_AFTER_SOWING_MIN_DAYS: Final[int] = 15
DRY_SPELL_AFTER_SOWING_MAX_DAYS: Final[int] = 20
"""The Sirsa rule's own 15-20 day band, used at the condition layer where we map
a modelled 5-day spell up to the DACP's wording."""

TERMINAL_DROUGHT_DOY_START: Final[int] = 250
"""Day-of-year after which a deficit is treated as terminal (grain fill /
maturity) rather than mid-season. ~September 7."""

UNSEASONAL_RAIN_RATIO: Final[float] = 3.0
"""Trailing 3-day rainfall this many times the pentad normal counts as
unseasonal. A ratio rather than an absolute threshold so it travels across
blocks with very different mean rainfall."""

LOW_SOIL_MOISTURE_FRACTION: Final[float] = 0.35
"""Below this fraction of available water, FAO-56 crops are in water stress for
most crop coefficients. Used as the moisture half of the drought conditions, so
that a dry *spell* alone does not fire a trigger if the profile is still wet --
which is the difference between a meteorological and an agricultural drought."""

# ---------------------------------------------------------------------------
# Panel schema -- the column contract every stage agrees on
# ---------------------------------------------------------------------------

COL_BLOCK: Final[str] = "block_id"
COL_DATE: Final[str] = "date"
COL_RAIN: Final[str] = "rain_mm"
COL_TMIN: Final[str] = "tmin_c"
COL_TMAX: Final[str] = "tmax_c"
COL_ENS_DRY_FRACTION: Final[str] = "ens_dry_fraction"
COL_RAIN_IMPUTED: Final[str] = "rain_is_imputed"

REQUIRED_OBSERVATION_COLUMNS: Final[tuple[str, ...]] = (
    COL_BLOCK,
    COL_DATE,
    COL_RAIN,
    COL_TMIN,
    COL_TMAX,
)

MODEL_VERSION: Final[str] = "trigger-engine/0.1.0"
"""Stamped onto every `DrySpellForecast`. A probability without a model version
cannot be audited after the fact."""

RANDOM_SEED: Final[int] = 42
"""Fixed seed for every stochastic operation, matching the reproducibility
practice from the load-forecasting benchmark."""
