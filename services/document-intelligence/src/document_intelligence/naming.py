"""Recover a district name from an ICAR-CRIDA DACP filename.

WHY THIS MODULE EXISTS

`scripts/ingest_all_dacp.py` recorded `pdf_path.stem` as the district, so the
corpus came out holding districts called `NL2-Wokha-20.11.2014` and
`ASSAM17-SIVASAGAR-26.7.2012`. Nothing downstream can look those up. The trigger
engine indexes rules on `(district, condition_code)`, and a district nobody can
name is a district nobody can serve -- measured directly: with filename
districts, `RuleStore.candidates("Wokha", ...)` returned 0 for all 645 documents
that were not the hand-special-cased Sirsa plan.

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
"""

from __future__ import annotations

import re

_SEPARATORS = re.compile(r"[-_\s]+")

_PURE_DIGITS = re.compile(r"^\d+$")

_LEADING_DIGITS = re.compile(r"^\d+")

# 26.07.14, 31-05-2011, 7/5/2016 -- any day/month/year triple, in any of the
# orders and separators the corpus uses.
_DATE_LIKE = re.compile(r"^\d{1,4}[.\-/]\d{1,2}[.\-/]\d{2,4}\.?$")

# UP50, BR35, CHH6, ASSAM17, HAR16 -- a state abbreviation glued to a serial.
_STATE_CODE_SERIAL = re.compile(r"^[A-Za-z]{1,6}\d+$")

_MIN_TOKEN_CHARS = 3
"""Tokens shorter than this are dropped. They are state abbreviations split by
the separator ("A", "N" from `A_N_1`), never districts -- no Indian district has
a name of one or two letters."""


def _fold(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def district_from_filename(stem: str, *, state: str | None = None) -> str:
    """Derive a readable district name from a DACP filename stem.

    Args:
        stem: The filename without its extension, e.g. `"NL2-Wokha-20.11.2014"`.
        state: The state the file was downloaded under, when known. Its name is
            removed from the token list -- several states put it in the filename
            (`Orissa_6-_Puri_31.05.2011`, `PUNJAB_13-Sangrur_30.04.2011`), where
            it would otherwise be mistaken for part of the district.

    Returns:
        The district in title case, e.g. `"Wokha"`, `"Lakhimpur Kheri"`. Falls
        back to the stem itself when subtraction removes everything -- a wrong
        name beats no name, because the name is also what the operator searches
        by, and an empty district would make the document unreachable rather
        than merely awkward.
    """
    state_tokens = {_fold(part) for part in _SEPARATORS.split(state or "") if _fold(part)}

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
        kept.append(trimmed.replace(".", ""))

    if not kept:
        return stem

    return " ".join(part.capitalize() if part.isupper() else part for part in kept)


def _is_state_prefix(token: str, state_tokens: set[str]) -> bool:
    """Whether a leading token is the state's name, an abbreviation of it, or a serial.

    Abbreviation is tested as a prefix (`guj` for Gujarat, `har` for Haryana)
    rather than by a lookup table of codes, because ICAR-CRIDA's codes are not
    published anywhere and are inconsistent between states.
    """
    folded = _fold(token)
    if not folded:
        return True
    if _PURE_DIGITS.match(folded) or _STATE_CODE_SERIAL.match(token):
        return True
    return any(
        folded == state or (len(folded) >= 2 and state.startswith(folded))
        for state in state_tokens
    )
