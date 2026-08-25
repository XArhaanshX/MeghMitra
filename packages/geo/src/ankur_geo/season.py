"""Monsoon season window: a project-scoped parameter, not a national constant.

`trigger_engine.config` hardcoded a single JJAS (June-September) window and
`preprocess.in_monsoon_window` used it as a row filter. That is correct for
Haryana -- the southwest monsoon is its whole rainy season -- and wrong for
Tamil Nadu, whose principal rains are the October-December northeast monsoon;
filtering TN's panel to JJAS silently discards its actual season.

`SeasonWindow` is the parameter that replaces the hardcoded constants. It does
NOT ship a national IMD onset/withdrawal-normals table -- that is real
per-met-subdivision data this environment cannot verify (see `districts.py`'s
note on the same problem for LGD codes). It ships exactly two defaults,
honestly labelled by what they are: the current Haryana/JJAS behaviour
(preserved bit-for-bit as `DEFAULT_SEASON_WINDOW`), and one demo/test profile
covering the northeast-monsoon shape so the parameterisation itself is
exercised end to end without inventing calibrated dates for every state.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SeasonWindow:
    """The window `preprocess.in_monsoon_window` filters a weather panel to.

    Mirrors the shape of the constants it replaces
    (`trigger_engine.config.MONSOON_START_MONTH` etc.) exactly, so a caller
    passing `DEFAULT_SEASON_WINDOW` reproduces today's behaviour with no
    numeric drift.
    """

    name: str
    start_month: int
    start_day: int
    end_month: int
    end_day: int

    @property
    def length_days(self) -> int:
        """Replaces the hardcoded `SEASON_LENGTH_DAYS = 122` -- derived, not
        transcribed, so a different window's Fourier phase anchor is correct
        automatically instead of silently reusing Haryana's."""
        from datetime import date

        end_year = 2001 if self.end_month >= self.start_month else 2002
        start = date(2001, self.start_month, self.start_day)
        end = date(end_year, self.end_month, self.end_day)
        return (end - start).days + 1


DEFAULT_SEASON_WINDOW = SeasonWindow(
    name="southwest_monsoon_jjas",
    start_month=6,
    start_day=1,
    end_month=9,
    end_day=30,
)
"""June 1 - September 30. Identical to the constants `trigger_engine.config`
hardcoded before this module existed -- the default preserves current
(Haryana) behaviour exactly."""

NORTHEAST_MONSOON_WINDOW = SeasonWindow(
    name="northeast_monsoon_ond",
    start_month=10,
    start_day=1,
    end_month=12,
    end_day=31,
)
"""October 1 - December 31. The shape of Tamil Nadu / Puducherry's principal
rainy season, used to exercise a non-JJAS panel in tests and the synthetic
demo profile -- not a calibrated IMD onset/withdrawal normal for any specific
district, which this environment has no verified source for."""
