"""District reference data: derived from the real DACP corpus, not fabricated.

WHY NOT A HAND-AUTHORED NATIONAL GAZETTEER

India has ~766 districts and the exact count changes as states split them.
This environment has no verified source for a complete, current district-to-
LGD-code table, and hand-typing ~750 rows from memory would be exactly the
kind of guessed geographic data the rest of this codebase refuses to produce
for DACP rule content. Instead, district identity here is *derived from the
documents Ankur has actually ingested* -- each is a government-published DACP
naming its own district and state, which is a real, checkable source.

This means `DISTRICTS` only covers districts with an ingested plan (currently
642 of ~766, per the 30 states/UTs with DACP coverage). A district with no
plan is not fabricated into existence; `resolve_region` reports the gap
honestly (see `resolve.py`) rather than inventing an identity for it.

`lgd_code` and `census_2011_code` are `int | None`, always `None` here --
populate them by importing an official LGD extract; never guess them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ankur_geo.alias import state_by_name_or_alias
from ankur_geo.fold import district_key, state_key
from ankur_geo.states import State

DEFAULT_PROCESSED_ROOT = Path("data/processed")


@dataclass(frozen=True, slots=True)
class District:
    """One district, as named by the DACP document(s) Ankur has ingested for it."""

    district_code: str
    """Stable slug identity: `"{state_code}-{district_slug}"`, e.g. `"KA-bijapur"`.
    Deterministic from (state, district) -- never regenerated arbitrarily, so
    it is safe to persist as a foreign key."""

    name: str
    slug: str
    state_code: str
    lgd_code: int | None = None
    census_2011_code: int | None = None


def _slugify(name: str) -> str:
    return district_key(name)


def build_district_index(root: Path | str = DEFAULT_PROCESSED_ROOT) -> tuple[District, ...]:
    """Scan an ingested corpus and derive one `District` per distinct (state, district)
    pair actually present.

    This is what produced the committed `DISTRICTS` snapshot below (see
    `scripts/generate_geo_reference.py`). Callers normally want the snapshot,
    not a fresh scan -- this function exists so the snapshot has a documented,
    reproducible generator rather than being hand-maintained.
    """
    # Two problems, same fix as `RuleStore.from_processed`: `data/processed`
    # can hold stale duplicate directories left over from a previous ingest
    # of the same source PDF (superseded, but not deleted), and the earliest
    # ingest run wrote the filename stem as the district ("AP1-Guntur_31.1.11")
    # before `naming.py` existed. Dedupe by source filename, newest first, so
    # a stale copy never contributes a bogus district.
    seen_source: dict[str, tuple[str, str]] = {}
    for path in sorted(Path(root).rglob("*.json"), key=lambda p: -p.stat().st_mtime):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))["document"]
        except Exception:  # noqa: BLE001 - a few unreadable files must not abort the scan
            continue
        source = document.get("filename")
        state_name = document.get("state")
        district_name = document.get("district")
        if not source or not state_name or not district_name:
            continue
        if source in seen_source:
            continue
        seen_source[source] = (state_name, district_name)

    seen: dict[tuple[str, str], tuple[str, str]] = {}
    for state_name, district_name in seen_source.values():
        matched_state = state_by_name_or_alias(state_name)
        skey = matched_state.state_code if matched_state else state_key(state_name)
        dkey = district_key(district_name)
        seen.setdefault((skey, dkey), (state_name, district_name))

    districts: list[District] = []
    for (skey, _dkey), (_state_name, district_name) in sorted(seen.items()):
        districts.append(
            District(
                district_code=f"{skey}-{_slugify(district_name)}",
                name=district_name,
                slug=_slugify(district_name),
                state_code=skey,
            )
        )
    return tuple(districts)


# Generated snapshot -- see scripts/generate_geo_reference.py. Committed so
# resolution does not depend on `data/processed` (326 MB, gitignored) being
# present at import time.
try:
    from ankur_geo._districts_generated import DISTRICTS
except ImportError:
    DISTRICTS = ()

DISTRICTS_BY_CODE: dict[str, District] = {d.district_code: d for d in DISTRICTS}

# (state_code, district_key) -> District, for fast exact lookup once a state
# is already known.
_DISTRICTS_BY_STATE_AND_KEY: dict[tuple[str, str], District] = {
    (d.state_code, district_key(d.name)): d for d in DISTRICTS
}

# district_key -> set of state_codes that have a district by this name.
# Non-singleton entries are the real duplicate-district-name collisions --
# 7 in the current corpus: Aurangabad (BR+MH), Balrampur (UP+CT), Bijapur
# (KA+CT), Bilaspur (CT+HP), Hamirpur (HP+UP), Pratapgarh (RJ+UP), Raigarh
# (MH+CT). Not an exhaustive national list -- just what this ~650-document
# corpus happens to contain; re-run `scripts/generate_geo_reference.py` after
# ingesting more states and this set may grow.
_STATE_CODES_BY_DISTRICT_KEY: dict[str, set[str]] = {}
for _d in DISTRICTS:
    _STATE_CODES_BY_DISTRICT_KEY.setdefault(district_key(_d.name), set()).add(_d.state_code)


def district_in_state(state: State, district_name: str) -> District | None:
    """Exact lookup: this district, in this specific state. Never falls back
    to a different state's same-named district."""
    return _DISTRICTS_BY_STATE_AND_KEY.get((state.state_code, district_key(district_name)))


def states_with_district_name(district_name: str) -> tuple[str, ...]:
    """State codes that have an ingested plan for a district with this name.

    Empty: the name is not in the corpus. One entry: unambiguous. More than
    one: this is one of the real cross-state duplicate names -- callers must
    not guess which state was meant.
    """
    return tuple(sorted(_STATE_CODES_BY_DISTRICT_KEY.get(district_key(district_name), ())))
