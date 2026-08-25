"""The rule base, as the trigger engine sees it: indexed by what it joins on.

WHY THIS MODULE EXISTS

`pipeline.emit_advisory` takes `candidate_rules` as an argument and, until now,
nothing in the repository supplied them. The ingestion pipeline wrote rules to
`data/processed/`; the trigger engine read from nowhere. This is the reader.

It is deliberately a *reader*, not a repository. `ankur_domain.repositories`
defines the Protocol the API implements against Postgres, and that is the right
home for anything the serving path mutates. This loads a corpus snapshot off
disk so the engine can be exercised, verified and demonstrated end to end
without a database -- the same reason `make test` never requires live Postgres.

THE INDEX IS THE POINT

Rules are keyed on `(state, district, condition_code)` because that triple is
exactly what `can_emit_advisory` checks: the rule must be for this district in
this state, and its `condition_code` must equal the code the weather produced.
Indexing on `(district, condition_code)` alone -- the original design -- looks
equivalent until two states have a same-named district (Bijapur exists in both
Karnataka and Chhattisgarh; Balrampur in both Uttar Pradesh and Chhattisgarh),
at which point `candidates()` silently returns the wrong state's contingency
plan. That is not a hypothetical: it reproduces on the real corpus. State is
therefore part of the index key, not an optional filter layered on top.

`UNMAPPED` rules are loaded and counted but are not reachable through
`candidates()`. They are a coverage measurement -- "this many rows say something
the engine has no predicate for" -- and keeping them countable but unservable is
the whole point of the code existing.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ankur_schemas.condition import EMITTABLE_CONDITION_CODES, ConditionCode
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.rule import DACPRule

logger = logging.getLogger(__name__)

DEFAULT_PROCESSED_ROOT = Path("data/processed")

_LEADING_INDEX = re.compile(r"^\d+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _fold_region_name(name: str) -> str:
    """Fold a region name to a stable lookup key.

    Region names reach us from three places that disagree: the DACP filename
    (`1North_Goa`, `HAR16-Sirsa-30-06-2011`), the download directory
    (`Andaman___Nicobar_Islands`), and whatever a caller types (`Sirsa`,
    `sirsa`, `Haryana`). Folding to lowercase alphanumerics, with any leading
    serial number stripped, makes those agree often enough to be useful.

    This is a lookup convenience and nothing more -- the key is never
    persisted and never shown to a user. It IS used to decide whether two
    rules answer the same lookup, which is exactly why both `district_key` and
    `state_key` must be combined: folding alone conflates same-named districts
    across different states.
    """
    cleaned = _LEADING_INDEX.sub("", name.strip())
    return _NON_ALNUM.sub("", cleaned.casefold())


def district_key(name: str) -> str:
    """Fold a district name to a stable lookup key. See `_fold_region_name`."""
    return _fold_region_name(name)


def state_key(name: str) -> str:
    """Fold a state name to a stable lookup key. See `_fold_region_name`.

    Always combined with `district_key` when indexing or looking up rules --
    never used alone, because district names collide across states.
    """
    return _fold_region_name(name)


@dataclass(frozen=True, slots=True)
class DocumentRef:
    """What the engine needs to know about a rule's source document.

    Only `page_count` is load-bearing: `can_emit_advisory` forwards it to
    `has_valid_citation`, which rejects a citation pointing past the end of the
    document it claims to quote. The Sirsa fixture cites page 44 of a 31-page
    plan, so this bound is not theoretical.
    """

    document_id: str
    filename: str
    district: str
    state: str
    page_count: int


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """What the corpus actually contains, stated in numbers rather than hopes.

    Written to be quotable in a status update without further arithmetic, and
    deliberately including the counts that look bad: `unmapped_rules` and
    `approved_rules` are the two that say how far this is from serving farmers.
    """
    documents: int
    rules: int
    approved_rules: int
    unmapped_rules: int
    districts: int
    district_name_collisions: int = 0
    """District names (folded) shared by more than one state in the loaded
    corpus -- e.g. Bijapur (Karnataka and Chhattisgarh). A nonzero count is a
    fact about India's districts, not a bug: several genuinely do repeat
    across states. It is surfaced so that fact is visible rather than
    discovered the hard way. What must never happen, regardless of this
    count, is `candidates()` returning one state's rules under another
    state's name -- guaranteed structurally because `_by_state_district_code`
    keys on `(state_key, district_key, code)`, not `district_key` alone."""
    by_code: dict[str, int] = field(default_factory=dict)
    by_review_status: dict[str, int] = field(default_factory=dict)

    @property
    def mapped_fraction(self) -> float:
        """Share of rules whose condition normalized to a servable code."""
        return 0.0 if self.rules == 0 else 1.0 - self.unmapped_rules / self.rules

    def summary_lines(self) -> list[str]:
        status_lines = [
            f"    {status:<26} {count}" for status, count in sorted(self.by_review_status.items())
        ]
        return [
            f"documents          {self.documents}",
            f"rules              {self.rules}",
            f"districts          {self.districts} "
            f"({self.district_name_collisions} name(s) shared across states)",
            f"condition mapped   {self.rules - self.unmapped_rules} "
            f"({100 * self.mapped_fraction:.1f}%)",
            f"unmapped           {self.unmapped_rules}",
            f"approved (human)   {self.approved_rules}",
            "by condition code:",
            *[f"    {code:<26} {count}" for code, count in sorted(self.by_code.items())],
            "by review status:",
            *status_lines,
        ]


@dataclass(slots=True)
class RuleStore:
    """An in-memory, read-only index over an ingested DACP corpus."""

    _by_state_district_code: dict[tuple[str, str, ConditionCode], list[DACPRule]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _documents: dict[str, DocumentRef] = field(default_factory=dict)
    _all_rules: list[DACPRule] = field(default_factory=list)

    @classmethod
    def from_processed(
        cls,
        root: Path | str = DEFAULT_PROCESSED_ROOT,
        *,
        districts: set[str] | None = None,
        states: set[str] | None = None,
    ) -> RuleStore:
        """Load every `*.json` written by `scripts/ingest_all_dacp.py`.

        Args:
            root: The processed-corpus directory.
            districts: Optional whitelist of district names (folded through
                `district_key`). Loading one district's rules is enough for a
                single-district run and skips ~640 files of parsing.
            states: Optional whitelist of state names (folded through
                `state_key`), ANDed with `districts` when both are given. Pass
                this whenever the district name alone could be ambiguous --
                which, on the real corpus, it can be (Bijapur, Balrampur,
                Pratapgarh, Raigarh each name a district in two different
                states). Omitting it is only safe when the caller has already
                confirmed the district name is unique in the loaded corpus.

        Returns:
            A populated store. A file that fails to parse is logged and skipped
            rather than aborting the load -- a corpus of 646 documents will
            contain a few surprises, and losing the other 645 to one of them
            helps nobody.
        """
        store = cls()
        wanted_districts = {district_key(name) for name in districts} if districts else None
        wanted_states = {state_key(name) for name in states} if states else None
        seen_source: dict[str, Path] = {}

        # Newest first, so that when the same source PDF appears twice the later
        # ingest wins and the earlier one is skipped. Re-ingesting after a change
        # to how districts are named leaves the previous run's files behind under
        # their old directory names, and loading both would double every rule and
        # index half of them under a district nobody can look up. Keyed on the
        # source PDF filename, which is unique across the ICAR-CRIDA corpus --
        # not on `document.id`, which is regenerated on every ingest.
        for path in sorted(Path(root).rglob("*.json"), key=lambda p: -p.stat().st_mtime):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                document = payload["document"]
                source = document["filename"]
                if source in seen_source:
                    logger.debug(
                        "skipping stale duplicate %s (superseded by %s)",
                        path,
                        seen_source[source],
                    )
                    continue
                seen_source[source] = path
                dkey = district_key(document["district"])
                skey = state_key(document["state"])
                if wanted_districts is not None and dkey not in wanted_districts:
                    continue
                if wanted_states is not None and skey not in wanted_states:
                    continue
                store._documents[document["id"]] = DocumentRef(
                    document_id=document["id"],
                    filename=document["filename"],
                    district=document["district"],
                    state=document["state"],
                    page_count=int(document["page_count"]),
                )
                for raw in payload["rules"]:
                    store._add(DACPRule.model_validate(raw), skey, dkey)
            except Exception:
                logger.warning("skipping unreadable processed file %s", path, exc_info=True)

        logger.info(
            "loaded %d rules from %d documents", len(store._all_rules), len(store._documents)
        )
        return store

    def _add(self, rule: DACPRule, state_key_val: str, district_key_val: str) -> None:
        self._all_rules.append(rule)
        code = rule.fields.condition_code
        if code is not None and code in EMITTABLE_CONDITION_CODES:
            self._by_state_district_code[(state_key_val, district_key_val, code)].append(rule)

    def candidates(self, state: str, district: str, code: ConditionCode) -> list[DACPRule]:
        """Rules for one district, in one state, that claim to answer one condition code.

        Returns `[]` for `UNMAPPED`, and for any state/district/code triple the
        corpus does not cover. Empty is a normal answer: `can_emit_advisory`
        turns it into "no matching approved rule" and the engine abstains,
        which is the correct behaviour when the plan is silent.

        Note what this does *not* do: it does not fall back to a neighbouring
        district, a different state's same-named district, or a "closest"
        condition. Retrieving a different district's contingency plan would be
        inventing advice, which is the one thing the product exists not to do
        -- and `state` is required precisely so that guarantee is real: a
        district-only lookup silently merges e.g. Bijapur, Karnataka with
        Bijapur, Chhattisgarh.
        """
        if code not in EMITTABLE_CONDITION_CODES:
            return []
        key = (state_key(state), district_key(district), code)
        return list(self._by_state_district_code.get(key, ()))

    def page_count_for(self, rule: DACPRule) -> int | None:
        """The source document's page count, for the citation bound.

        None when the document is unknown, which `has_valid_citation` treats as
        "no bound available" rather than as a failure -- the bound is a
        tightening, and a missing tightening must not become a rejection.
        """
        if rule.document_id is None:
            return None
        reference = self._documents.get(str(rule.document_id))
        return None if reference is None else reference.page_count

    @property
    def rules(self) -> list[DACPRule]:
        return list(self._all_rules)

    @property
    def documents(self) -> list[DocumentRef]:
        return list(self._documents.values())

    def districts(self) -> list[str]:
        """District names present in the corpus, as the documents spell them."""
        return sorted({reference.district for reference in self._documents.values()})

    def states_for_district(self, district: str) -> list[str]:
        """States (as spelled by their documents) that publish a plan for this district name.

        Empty means the district is not in the corpus. More than one entry
        means the name is ambiguous and a caller must supply `state` before
        calling `candidates()` -- this is what lets a CLI resolve `--state`
        automatically when the answer is unambiguous, and demand it loudly
        when it is not.
        """
        wanted = district_key(district)
        return sorted(
            {
                reference.state
                for reference in self._documents.values()
                if district_key(reference.district) == wanted
            }
        )

    def coverage(self) -> CoverageReport:
        """Measure the corpus. See `CoverageReport` for why the bad numbers are in it."""
        by_code = Counter(
            (rule.fields.condition_code or ConditionCode.UNMAPPED).value
            for rule in self._all_rules
        )
        by_status = Counter(rule.review_status.value for rule in self._all_rules)
        district_states: dict[str, set[str]] = defaultdict(set)
        for reference in self._documents.values():
            district_states[district_key(reference.district)].add(state_key(reference.state))
        collisions = sum(1 for states in district_states.values() if len(states) > 1)
        return CoverageReport(
            documents=len(self._documents),
            rules=len(self._all_rules),
            approved_rules=sum(
                1 for rule in self._all_rules if rule.review_status == ReviewStatus.APPROVED
            ),
            unmapped_rules=by_code.get(ConditionCode.UNMAPPED.value, 0),
            districts=len(district_states),
            district_name_collisions=collisions,
            by_code=dict(by_code),
            by_review_status=dict(by_status),
        )
