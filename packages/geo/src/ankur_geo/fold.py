"""The single fold used everywhere a state or district name becomes a lookup key.

This used to be duplicated (district-only) inside `trigger_engine.rulestore`.
It now lives here so every layer that needs to compare a state/district name --
the trigger engine's rule store, `document_intelligence.naming`, the API's
`resolve_region`, and the frontend's server-side lookups -- agrees on exactly
one definition. `trigger_engine.rulestore.district_key`/`state_key` re-export
this module's functions rather than redefining them.
"""

from __future__ import annotations

import re

_LEADING_INDEX = re.compile(r"^\d+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def fold_region_name(name: str) -> str:
    """Fold a state or district name to a stable lookup key.

    Region names reach us from several places that disagree: a DACP filename
    (`1North_Goa`, `HAR16-Sirsa-30-06-2011`), a download directory
    (`Andaman___Nicobar_Islands`), and whatever a caller types (`Sirsa`,
    `sirsa`, `Haryana`). Folding to lowercase alphanumerics, with any leading
    serial number stripped, makes those agree often enough to be useful.

    This is a lookup convenience, not an identity. It IS used to decide
    whether two rules answer the same lookup, which is exactly why a district
    fold must always be combined with a state fold -- folding district names
    alone conflates Bijapur (Karnataka) with Bijapur (Chhattisgarh).
    """
    cleaned = _LEADING_INDEX.sub("", name.strip())
    return _NON_ALNUM.sub("", cleaned.casefold())


def state_key(name: str) -> str:
    """Fold a state/UT name. See `fold_region_name`."""
    return fold_region_name(name)


def district_key(name: str) -> str:
    """Fold a district name. See `fold_region_name`."""
    return fold_region_name(name)
