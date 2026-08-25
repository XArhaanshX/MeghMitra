"""The single region-resolution function every layer should call.

`resolve_region` never guesses. Given a state name and a district name it
either returns a `ResolvedRegion` naming both unambiguously, or raises
`RegionResolutionError` explaining exactly why not -- unknown state, unknown
district, or (the case that matters most) a district name that exists under a
*different* state than the one given. Guessing in that last case is precisely
the bug Phase 0 fixed in `RuleStore`; this function is the reusable version of
the same discipline for every other caller (ingestion, the API, the CLI).
"""

from __future__ import annotations

from dataclasses import dataclass

from ankur_geo.alias import state_by_name_or_alias
from ankur_geo.districts import District, district_in_state, states_with_district_name
from ankur_geo.states import State, state_by_code


class RegionResolutionError(ValueError):
    """A state or district name could not be resolved. Never guessed away."""


@dataclass(frozen=True, slots=True)
class ResolvedRegion:
    state: State
    district: District


def resolve_state(state_text: str) -> State:
    """Resolve a state/UT name, including the 7 known legacy spellings.

    Raises `RegionResolutionError` for anything else -- an unrecognized state
    name is a data problem to surface, not a guess to paper over.
    """
    matched = state_by_name_or_alias(state_text)
    if matched is not None:
        return matched
    raise RegionResolutionError(
        f"Unrecognized state/UT name: {state_text!r}. Not one of the 36 canonical "
        "names and not a known legacy alias."
    )


def resolve_region(state_text: str, district_text: str) -> ResolvedRegion:
    """Resolve a (state, district) pair to canonical identity.

    Raises `RegionResolutionError` if the state is unrecognized, or if the
    district is not an ingested district of that specific state -- including
    when it IS an ingested district of a *different* state, which is the
    exact ambiguity a district-only lookup would silently mishandle.
    """
    state = resolve_state(state_text)
    district = district_in_state(state, district_text)
    if district is not None:
        return ResolvedRegion(state=state, district=district)

    other_state_codes = [
        code for code in states_with_district_name(district_text) if code != state.state_code
    ]
    if other_state_codes:
        other_names = ", ".join(
            match.name for code in other_state_codes if (match := state_by_code(code))
        )
        raise RegionResolutionError(
            f"{district_text!r} is not an ingested district of {state.name}. A district "
            f"by this name IS ingested for: {other_names}. Refusing to guess which state "
            "was meant -- pass the correct state explicitly."
        )
    raise RegionResolutionError(
        f"{district_text!r} is not an ingested district of {state.name}, and no plan "
        "for a district by this name is loaded for any state."
    )
