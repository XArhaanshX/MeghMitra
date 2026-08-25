"""India-wide geographic reference data and resolution.

    fold        state_key / district_key -- the single fold used everywhere
    states      the 36 states/UTs, ISO 3166-2:IN identity
    districts   districts derived from the ingested DACP corpus
    alias       legacy state-name spellings found in the raw corpus
    resolve     resolve_region() -- the one function that turns free-text
                (state, district) into canonical identity, raising rather
                than guessing when it cannot
    season      SeasonWindow -- replaces the hardcoded JJAS constants
    thresholds  ConditionThresholds -- replaces the Sirsa-derived condition
                detection constants
    bbox        INDIA_BBOX -- the one place a map default may come from
"""

from ankur_geo.alias import DISTRICT_STATE_OVERRIDES, STATE_NAME_ALIASES, state_by_name_or_alias
from ankur_geo.bbox import INDIA_BBOX
from ankur_geo.districts import (
    DISTRICTS,
    DISTRICTS_BY_CODE,
    District,
    district_in_state,
    states_with_district_name,
)
from ankur_geo.fold import district_key, fold_region_name, state_key
from ankur_geo.resolve import RegionResolutionError, ResolvedRegion, resolve_region, resolve_state
from ankur_geo.season import DEFAULT_SEASON_WINDOW, NORTHEAST_MONSOON_WINDOW, SeasonWindow
from ankur_geo.states import STATES, STATES_BY_CODE, RegionKind, State, state_by_code, state_by_name
from ankur_geo.thresholds import DEFAULT_CONDITION_THRESHOLDS, ConditionThresholds

__all__ = [
    "DEFAULT_CONDITION_THRESHOLDS",
    "DEFAULT_SEASON_WINDOW",
    "DISTRICTS",
    "DISTRICTS_BY_CODE",
    "DISTRICT_STATE_OVERRIDES",
    "INDIA_BBOX",
    "NORTHEAST_MONSOON_WINDOW",
    "STATES",
    "STATES_BY_CODE",
    "STATE_NAME_ALIASES",
    "ConditionThresholds",
    "District",
    "RegionKind",
    "RegionResolutionError",
    "ResolvedRegion",
    "SeasonWindow",
    "State",
    "district_in_state",
    "district_key",
    "fold_region_name",
    "resolve_region",
    "resolve_state",
    "state_by_code",
    "state_by_name",
    "state_by_name_or_alias",
    "state_key",
    "states_with_district_name",
]
