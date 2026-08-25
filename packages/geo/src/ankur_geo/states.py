"""India's 28 states and 8 union territories: canonical identity.

CODE CHOICE

`state_code` is the ISO 3166-2:IN subdivision code without its `IN-` prefix
(e.g. `"HR"` for Haryana), not a Local Government Directory (LGD) numeric
code. This is a deliberate, documented deviation from the originally-proposed
"use LGD codes" plan: LGD codes are the right *long-term* identity (maintained
by the Ministry of Panchayati Raj, and the correct join key for most published
government datasets), but this codebase has no verified source for the exact
LGD numbers in this environment, and fabricating them would be exactly the
kind of guessed-not-nullable value `AGENTS.md` prohibits for DACP rule fields.
ISO 3166-2:IN codes are a public, checkable standard and are stable identity
today.

`lgd_code` is kept as an explicit `int | None` field, `None` until a real LGD
extract is imported. Nullable over guessed, same principle the rule extractor
already applies to `DACPRuleFields`.

The 2020 merger of Dadra & Nagar Haveli and Daman & Diu is represented as one
union territory, `DH`, per the post-merger ISO update.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ankur_geo.fold import state_key


class RegionKind(StrEnum):
    STATE = "state"
    UNION_TERRITORY = "union_territory"


@dataclass(frozen=True, slots=True)
class State:
    """A state or union territory of India."""

    state_code: str
    """ISO 3166-2:IN subdivision code, without the `IN-` prefix, e.g. `"HR"`."""

    name: str
    slug: str
    kind: RegionKind
    lgd_code: int | None = None
    """Local Government Directory numeric code. `None` until imported from an
    official LGD extract -- never guessed."""
    census_2011_code: int | None = None
    """Census of India 2011 state code. `None` for post-2011 entities
    (Telangana, and the post-2019 J&K/Ladakh split) which the 2011 census
    cannot represent, and for any state not yet cross-referenced."""


# fmt: off
STATES: tuple[State, ...] = (
    State("AP", "Andhra Pradesh", "andhra-pradesh", RegionKind.STATE),
    State("AR", "Arunachal Pradesh", "arunachal-pradesh", RegionKind.STATE),
    State("AS", "Assam", "assam", RegionKind.STATE),
    State("BR", "Bihar", "bihar", RegionKind.STATE),
    State("CT", "Chhattisgarh", "chhattisgarh", RegionKind.STATE),
    State("GA", "Goa", "goa", RegionKind.STATE),
    State("GJ", "Gujarat", "gujarat", RegionKind.STATE),
    State("HR", "Haryana", "haryana", RegionKind.STATE),
    State("HP", "Himachal Pradesh", "himachal-pradesh", RegionKind.STATE),
    State("JH", "Jharkhand", "jharkhand", RegionKind.STATE),
    State("KA", "Karnataka", "karnataka", RegionKind.STATE),
    State("KL", "Kerala", "kerala", RegionKind.STATE),
    State("MP", "Madhya Pradesh", "madhya-pradesh", RegionKind.STATE),
    State("MH", "Maharashtra", "maharashtra", RegionKind.STATE),
    State("MN", "Manipur", "manipur", RegionKind.STATE),
    State("ML", "Meghalaya", "meghalaya", RegionKind.STATE),
    State("MZ", "Mizoram", "mizoram", RegionKind.STATE),
    State("NL", "Nagaland", "nagaland", RegionKind.STATE),
    State("OD", "Odisha", "odisha", RegionKind.STATE),
    State("PB", "Punjab", "punjab", RegionKind.STATE),
    State("RJ", "Rajasthan", "rajasthan", RegionKind.STATE),
    State("SK", "Sikkim", "sikkim", RegionKind.STATE),
    State("TN", "Tamil Nadu", "tamil-nadu", RegionKind.STATE),
    State("TG", "Telangana", "telangana", RegionKind.STATE),
    State("TR", "Tripura", "tripura", RegionKind.STATE),
    State("UP", "Uttar Pradesh", "uttar-pradesh", RegionKind.STATE),
    State("UT", "Uttarakhand", "uttarakhand", RegionKind.STATE),
    State("WB", "West Bengal", "west-bengal", RegionKind.STATE),
    State(
        "AN",
        "Andaman and Nicobar Islands",
        "andaman-and-nicobar-islands",
        RegionKind.UNION_TERRITORY,
    ),
    State("CH", "Chandigarh", "chandigarh", RegionKind.UNION_TERRITORY),
    State(
        "DH",
        "Dadra and Nagar Haveli and Daman and Diu",
        "dadra-and-nagar-haveli-and-daman-and-diu",
        RegionKind.UNION_TERRITORY,
    ),
    State("DL", "Delhi", "delhi", RegionKind.UNION_TERRITORY),
    State("JK", "Jammu and Kashmir", "jammu-and-kashmir", RegionKind.UNION_TERRITORY),
    State("LA", "Ladakh", "ladakh", RegionKind.UNION_TERRITORY),
    State("LD", "Lakshadweep", "lakshadweep", RegionKind.UNION_TERRITORY),
    State("PY", "Puducherry", "puducherry", RegionKind.UNION_TERRITORY),
)
# fmt: on

STATES_BY_CODE: dict[str, State] = {state.state_code: state for state in STATES}
_STATES_BY_KEY: dict[str, State] = {state_key(state.name): state for state in STATES}

assert len(STATES) == 36, "India has 28 states + 8 union territories = 36"
assert len(STATES_BY_CODE) == 36, "state_code values must be unique"


def state_by_code(code: str) -> State | None:
    return STATES_BY_CODE.get(code.upper())


def state_by_name(name: str) -> State | None:
    """Look up a state by its canonical name, folded. Returns `None` -- never
    a guess -- when the name does not match any of the 36 entries."""
    return _STATES_BY_KEY.get(state_key(name))
