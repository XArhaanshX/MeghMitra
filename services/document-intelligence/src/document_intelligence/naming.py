"""Recover a district name from an ICAR-CRIDA DACP filename.

WHY THIS MODULE EXISTS

`scripts/ingest_all_dacp.py` recorded `pdf_path.stem` as the district, so the
corpus came out holding districts called `NL2-Wokha-20.11.2014` and
`ASSAM17-SIVASAGAR-26.7.2012`. Nothing downstream can look those up. The trigger
engine indexes rules on `(state, district, condition_code)`, and a district
nobody can name is a district nobody can serve -- measured directly: with
filename districts, `RuleStore.candidates(...)` returned 0 for all 645
documents that were not the hand-special-cased Sirsa plan.

WHAT THE NAMES LOOK LIKE

ICAR-CRIDA names files as `<state-code><serial>-<district>-<date>.pdf`, with `-`
and `_` used interchangeably as separators and the date in any of a half-dozen
formats:

    UP50-Mahoba-26.07.14.pdf          -> Mahoba
    UP67-Lakhimpur_Kheri-31.07.14.pdf -> Lakhimpur Kheri
    Orissa_6-_Puri_31.05.2011.pdf     -> Puri
    A_N_1-Nicobar-03.05.2015.pdf      -> Nicobar
    AR6-Upper_Siang-01.07.2015.pdf    -> Upper Siang
    1North_Goa.pdf                    -> North Goa

So the district is what is left after removing the parts that are demonstrably
not a district: serials, dates, the state's own name, and the short alphabetic
codes that stand in for it.

SUBTRACTIVE, NOT EXTRACTIVE

The parser removes known-junk tokens and keeps the remainder, rather than trying
to match a district against a gazetteer of Indian district names. A gazetteer
would be more precise and would fail worse: districts get renamed, split and
respelled, and a name the list did not contain would be dropped silently. Here
an unrecognized token is *kept*, so the failure mode is a district name with an
extra word in it -- visible, and harmless to the citation, which is keyed on the
document rather than on the name.

`state` IS REQUIRED

Measured on the real corpus: with `state=None`, a state-name token survives
into the district ("Puri" becomes "Orissa Puri") whenever the download
directory's name is not itself glued to a serial. There is no filename shape
where omitting `state` produces a *better* result than passing it, so the
parameter is required rather than optional -- a caller with no state to give
has a data problem worth surfacing, not one worth guessing past.

`state` MAY BE MISSPELLED; THE FILENAME MAY NOT MATCH IT

`data/raw/`'s own directory names include real misspellings (`Maharastra` for
Maharashtra, `Chattisgarh` for Chhattisgarh, `Orissa` for the pre-1996 name of
Odisha). A filename can spell the state correctly even when its directory
does not (`Maharashtra_26-Aurangabad-...pdf` under `Maharastra/`), so
comparing only against the raw `state` argument as typed fails to strip it --
"Maharashtra" survives into the district as "Maharashtra Aurangabad". This
module tries to canonicalize `state` through `ankur_geo` (exact match, then
the known legacy-spelling aliases) and, when that succeeds, matches against
*both* spellings. Canonicalization failure is not fatal here -- naming still
falls back to matching the raw `state` string alone, because a subtractive
parser degrading to "keep an extra token" is safe; `resolve_region` is the
function that raises on an unresolvable state, not this one.
"""

from __future__ import annotations

import re

from ankur_geo.alias import state_by_name_or_alias

_SEPARATORS = re.compile(r"[-_\s]+")

_PURE_DIGITS = re.compile(r"^\d+$")

_LEADING_DIGITS = re.compile(r"^\d+")

_TRAILING_DIGITS = re.compile(r"\d+$")

# 26.07.14, 31-05-2011, 7/5/2016 -- any day/month/year triple, in any of the
# orders and separators the corpus uses.
_DATE_LIKE = re.compile(r"^\d{1,4}[.\-/]\d{1,2}[.\-/]\d{2,4}\.?$")

# UP50, BR35, CHH6, ASSAM17, HAR16 -- a state abbreviation glued to a serial.
_STATE_CODE_SERIAL = re.compile(r"^[A-Za-z]{1,6}\d+$")

_MIN_TOKEN_CHARS = 3
"""Tokens shorter than this are dropped. They are state abbreviations split by
the separator ("A", "N" from `A_N_1`), never districts -- no Indian district has
a name of one or two letters."""

_JUNK_WORDS = {"draft", "plan"}
"""Not a district, not a state, not a serial: template boilerplate a handful
of filenames carry (`CHH13-Dhamtari_draft_plan-10.07.14.pdf`). Measured on the
real corpus: 13 documents, mostly Chhattisgarh/UP draft plans, that carried
"Draft Plan" straight into the district name without this."""


def _fold(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _canonical_state_tokens(state: str) -> set[str]:
    """Every spelling of `state` worth stripping from a filename: as given,
    plus its canonical name when `ankur_geo` can resolve it (exact match or a
    known legacy alias). Never raises -- see module docstring."""
    tokens = {_fold(part) for part in _SEPARATORS.split(state) if _fold(part)}
    matched = state_by_name_or_alias(state)
    if matched is not None:
        tokens |= {_fold(part) for part in _SEPARATORS.split(matched.name) if _fold(part)}
    return tokens


def district_from_filename(stem: str, *, state: str) -> str:
    """Derive a readable district name from a DACP filename stem.

    Args:
        stem: The filename without its extension, e.g. `"NL2-Wokha-20.11.2014"`.
        state: The state the file was downloaded under. Required -- see the
            module docstring for why. Every spelling `ankur_geo` can resolve
            it to (as typed, plus its canonical name if different) is removed
            from the token list -- several states put it in the filename
            (`Orissa_6-_Puri_31.05.2011`, `PUNJAB_13-Sangrur_30.04.2011`),
            where it would otherwise be mistaken for part of the district.

    Returns:
        The district in title case, e.g. `"Wokha"`, `"Lakhimpur Kheri"`. Falls
        back to the stem itself when subtraction removes everything -- a wrong
        name beats no name, because the name is also what the operator searches
        by, and an empty district would make the document unreachable rather
        than merely awkward.
    """
    state_tokens = _canonical_state_tokens(state)

    tokens = [token for token in _SEPARATORS.split(stem) if token]

    # The state's name is stripped only from the *front*. Several states prefix
    # it (`Orissa_6-_Puri`, `PUNJAB_13-Sangrur`, `GUJ_6-Porbandar`), but two
    # districts are genuinely named after their state -- Nicobar in Andaman &
    # Nicobar Islands, North Goa in Goa -- and removing it everywhere deleted
    # exactly the word that identified them.
    while tokens and _is_state_prefix(tokens[0], state_tokens):
        tokens.pop(0)

    kept: list[str] = []
    for token in tokens:
        # A leading serial is glued to the name in some states (`1North_Goa`).
        trimmed = _LEADING_DIGITS.sub("", token).strip(".")
        if not trimmed:
            continue
        if _PURE_DIGITS.match(trimmed) or _DATE_LIKE.match(token):
            continue
        if _STATE_CODE_SERIAL.match(token):
            continue
        if len(trimmed) < _MIN_TOKEN_CHARS:
            continue
        if trimmed.casefold() in _JUNK_WORDS:
            continue
        kept.append(trimmed.replace(".", ""))

    if not kept:
        return stem

    return " ".join(part.capitalize() if part.isupper() else part for part in kept)


def _is_state_prefix(token: str, state_tokens: set[str]) -> bool:
    """Whether a leading token is the state's name, an abbreviation of it, or a serial.

    Abbreviation is tested as a prefix (`guj` for Gujarat, `har` for Haryana)
    rather than by a lookup table of codes, because ICAR-CRIDA's codes are not
    published anywhere and are inconsistent between states. Trailing digits
    are stripped before comparison (`Rajasthan23` -> `rajasthan`) so a serial
    glued to the full state name, not just its code, is still recognized --
    without this, `Rajasthan23-Banswara-5.7.2012.pdf` kept "Rajasthan23" as
    part of the district.
    """
    folded = _fold(token)
    if not folded:
        return True
    if _PURE_DIGITS.match(folded) or _STATE_CODE_SERIAL.match(token):
        return True
    unserialed = _TRAILING_DIGITS.sub("", folded)
    return any(
        candidate == state or (len(candidate) >= 2 and state.startswith(candidate))
        for state in state_tokens
        for candidate in (folded, unserialed)
    )
