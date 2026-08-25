"""Legacy / non-canonical state name aliases seen in the DACP corpus.

`scripts/download_dacp.py` filed PDFs under `data/raw/<State>/` using the
state name as it appeared wherever the plan was sourced from, not a
canonicalised name. Seven of the resulting directory names do not fold to
any of the 36 canonical `ankur_geo.states.STATES` entries:

    Arunchal_Pradesh          typo for Arunachal Pradesh
    Chattisgarh               historical/informal spelling of Chhattisgarh
    Maharastra                typo for Maharashtra
    Orissa                    pre-1996 name for Odisha
    Uttarkhand                typo for Uttarakhand
    Jammu___Kashmir           pre-2019 J&K, before the Ladakh split
    Andaman___Nicobar_Islands underscore-joined "&"

This table is consulted by `resolve.py` whenever an exact fold against the
canonical state list fails. It does not grow silently -- an unresolvable name
is a resolution failure (see `resolve_region`), never a guess.

LADAKH: pre-2019 J&K DACPs (`data/raw/Jammu___Kashmir/`) include Leh and
Kargil, which are now Ladakh's districts under the post-2019 boundary. This
module does not attempt to auto-split them: `J_K9-Leh-10.08.12.pdf` and
`JK6-Kargil-10.08.12.pdf` resolve to state `Jammu and Kashmir` (their
document's own stated state, which is what the DACP itself says) until an
explicit district-level override is added. Silently reassigning them to
Ladakh would be inferring a boundary change the document does not state --
exactly what `AGENTS.md` prohibits for rule content, extended here to
geography.
"""

from __future__ import annotations

from ankur_geo.fold import fold_region_name
from ankur_geo.states import State, state_by_code, state_by_name

# folded legacy name -> canonical state_code
STATE_NAME_ALIASES: dict[str, str] = {
    "arunchalpradesh": "AR",
    "chattisgarh": "CT",
    "maharastra": "MH",
    "orissa": "OD",
    "uttarkhand": "UT",
    "jammukashmir": "JK",
    "andamannicobarislands": "AN",
}

DISTRICT_STATE_OVERRIDES: dict[tuple[str, str], str] = {}
"""(state_code as ingested, folded district name) -> corrected state_code.
Empty today. Reserved for the Ladakh split once/if it is made explicit
(see module docstring) -- never populated by inference."""


def state_by_name_or_alias(name: str) -> State | None:
    """Resolve a state/UT name against the canonical list, then the legacy
    aliases above. Returns `None` -- never a guess -- for anything else.

    This is the ONE place canonical-plus-alias state resolution happens.
    `resolve.py`, `districts.py`'s corpus scanner, and
    `document_intelligence.naming` all call this instead of duplicating the
    two-step lookup, so a state spelling that resolves in one place resolves
    identically everywhere.
    """
    matched = state_by_name(name)
    if matched is not None:
        return matched
    code = STATE_NAME_ALIASES.get(fold_region_name(name))
    return state_by_code(code) if code else None
