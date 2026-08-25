"""National map default, so no UI or ML call site hardcodes a centre/zoom."""

from __future__ import annotations

INDIA_BBOX: tuple[float, float, float, float] = (68.1, 6.5, 97.4, 35.5)
"""(min_lon, min_lat, max_lon, max_lat), WGS84 -- mainland extent including
the Andaman & Nicobar and Lakshadweep island groups. Any viewport that would
otherwise default to a fixed centre/zoom should derive one from this bbox (or
from a selected state/district's own bbox) instead."""
