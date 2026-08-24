"""Chunks -> `DACPRuleDraft`s.

This is a deterministic, heuristic table-row extractor -- not an LLM, not a
chatbot. DACP contingency tables are read column-by-column against a small
known-header vocabulary; a table row is only mapped into a field when its
column header was actually recognized on a preceding header row of the same
page. If no header context exists, the row is preserved verbatim as the
`condition` text and routed to review rather than guessed at.

TWO PATHS, IN ORDER

`extract_rules` tries geometric table reconstruction first (`tables.py`) and
falls back to the original line-level path when that finds no readable table.

The geometric path exists because the line-level one cannot represent a wrapped
table cell. A DACP condition routinely spans four lines, and read line by line it
becomes four rules holding four sentence fragments -- measured on the Sirsa plan,
450 "rules" from 31 pages, none of them joinable to anything. Reconstructing the
columns first yields ~34 rules from the same pages, with conditions like "Normal
onset followed by 15-20 days dry spell after sowing leading to poor
germination/crop stand etc." intact.

The fallback is kept rather than deleted because it degrades in the safe
direction: a page whose columns cannot be located still produces its text as
`condition`, at low confidence, routed to a human. Silence about a page we
failed to parse would be worse than a review item.

NORMALIZATION HAPPENS HERE

Both paths set `condition_code` via `normalize.explain_normalization`. That field
is the only thing `trigger_engine` joins on, and until it was populated the rule
base could not drive an advisory at all -- see `normalize.py`'s docstring.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ankur_schemas.citation import Citation
from ankur_schemas.condition import ConditionCode
from ankur_schemas.document import DocumentMetadata, DocumentPage
from ankur_schemas.enums import SourceKind
from ankur_schemas.rule import DACPRuleDraft, DACPRuleFields

from document_intelligence.chunker import Chunk
from document_intelligence.confidence import score_draft
from document_intelligence.normalize import explain_normalization, normalize_condition
from document_intelligence.tables import (
    AssembledRow,
    assemble_rows,
    column_bands,
    find_table_regions,
    header_labels,
)

EXTRACTOR_VERSION = "document-intelligence/0.2.0"
"""Bumped from 0.1.0 when geometric table reconstruction and condition
normalization landed. The version is stamped on every draft, so a rule extracted
before this change stays distinguishable from one extracted after -- which
matters when re-ingesting a corpus a reviewer has already worked through."""

MAX_CELL_CHARS = 2000
"""Upper bound on a reassembled cell before it is truncated with an ellipsis.

The rightmost column of a DACP table is free-text remarks, and where a region
runs long its cell can absorb most of a page. Truncation is a storage and display
concern only: the citation still names the page, so nothing becomes
unverifiable."""

# Normalized header text -> DACPRuleFields attribute. Order doesn't matter;
# first substring match wins. Kept flat and explicit rather than fuzzy-matched
# so the mapping is auditable.
_HEADER_KEYWORDS: dict[str, str] = {
    "block": "block",
    "taluka": "block",
    "farming situation": "farming_situation",
    "crop": "crop",
    "soil": "soil",
    "stage": "crop_stage",
    "growth stage": "crop_stage",
    "condition": "condition",
    "weather aberration": "condition",
    "rainfall situation": "condition",
    "eventuality": "condition",
    "contingency measure": "action",
    "suggested action": "action",
    "suggested contingency measure": "action",
    "action": "action",
    "technology option": "action",
    "variety": "variety",
    "seed rate": "seed_rate",
    "responsible": "actor",
    "actor": "actor",
    "implementing agency": "actor",
}


def _normalize(cell: str) -> str:
    return " ".join(cell.strip().lower().split())


def _match_header_field(cell: str) -> str | None:
    normalized = _normalize(cell)
    for keyword, field in _HEADER_KEYWORDS.items():
        if keyword in normalized:
            return field
    return None


def _is_header_row(columns: list[str]) -> bool:
    """A header row must include a recognized 'condition' column plus at
    least one other known column -- this is what distinguishes a DACP
    contingency-measures table header from an unrelated 2-column table
    elsewhere in the document (land use, irrigation sources, etc.), which
    would otherwise be mis-detected as a rule table.
    """
    matched = {field for cell in columns if (field := _match_header_field(cell)) is not None}
    return "condition" in matched and len(matched) >= 2


def _map_row(columns: list[str], header_fields: list[str | None]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for cell, field in zip(columns, header_fields, strict=False):
        if field is None:
            continue
        value = cell.strip()
        if value and value not in {"-", "--", "NA", "N/A"}:
            mapped[field] = value
    return mapped


_EMPTY_CELL_MARKERS = frozenset({"-", "--", "---", "-do-", "na", "n/a", "nil", "none"})
"""Cell contents that mean "nothing here". `-do-` is ditto notation, common in
these tables; treating it as a value would copy the wrong text into a field."""


def _clip(text: str) -> str:
    """Bound a reassembled cell, marking the cut so nobody mistakes it for the end."""
    stripped = text.strip()
    if len(stripped) <= MAX_CELL_CHARS:
        return stripped
    return stripped[:MAX_CELL_CHARS].rstrip() + " [...]"


def _cell_or_none(text: str) -> str | None:
    """Normalize an empty-ish cell to None.

    Nullable over guessed: a DACP simply may not specify a variety or a seed
    rate, and `null` says that honestly where an empty string would look like an
    extracted value that happened to be blank.
    """
    stripped = text.strip()
    if not stripped or stripped.lower() in _EMPTY_CELL_MARKERS:
        return None
    return _clip(stripped)


def _fields_from_row(
    row: AssembledRow,
    field_by_column: list[str | None],
    document: DocumentMetadata,
) -> DACPRuleFields | None:
    """Project one reassembled row onto `DACPRuleFields`.

    Columns whose title was recognized go to their field. Columns whose title was
    not recognized are appended to `action` rather than dropped -- the DACP's
    right-hand columns are all variations on "what to do", their titles differ by
    state ("Agronomic measures", "Crop management", "Soil nutrient & moisture
    conservation measures"), and losing one loses the advice itself. Over-broad
    beats absent here: the text is still verbatim and still cited.

    Returns None when the row has no usable condition, which is the one field
    that cannot be reconstructed from anything else.
    """
    collected: dict[str, list[str]] = {}
    unmapped: list[str] = []

    for index, raw in enumerate(row.cells):
        value = _cell_or_none(raw)
        if value is None:
            continue
        field = field_by_column[index] if index < len(field_by_column) else None
        if field is None:
            unmapped.append(value)
        else:
            collected.setdefault(field, []).append(value)

    condition = " ".join(collected.get("condition", []))
    if not condition.strip():
        # The anchor column is the condition by construction (`assemble_rows`
        # keeps only rows with a non-empty anchor), so fall back to it when the
        # header text was too mangled to recognize.
        condition = _cell_or_none(row.cells[0]) or ""
    if not condition.strip():
        return None

    action_parts = collected.get("action", []) + unmapped
    action = " | ".join(action_parts) if action_parts else None

    return DACPRuleFields(
        district=document.district,
        block=_join_or_none(collected.get("block")),
        farming_situation=_join_or_none(collected.get("farming_situation")),
        crop=_join_or_none(collected.get("crop")),
        soil=_join_or_none(collected.get("soil")),
        crop_stage=_join_or_none(collected.get("crop_stage")),
        condition=_clip(condition),
        action=_clip(action) if action else None,
        variety=_join_or_none(collected.get("variety")),
        seed_rate=_join_or_none(collected.get("seed_rate")),
        actor=_join_or_none(collected.get("actor")),
    )


def _join_or_none(parts: list[str] | None) -> str | None:
    return _clip(" ".join(parts)) if parts else None


def _merge_rows(rows: list[AssembledRow]) -> AssembledRow:
    """Concatenate several assembled rows column-wise into one."""
    width = max(len(row.cells) for row in rows)
    cells = [
        " ".join(row.cells[index] for row in rows if index < len(row.cells) and row.cells[index])
        for index in range(width)
    ]
    return AssembledRow(
        cells=cells,
        source_lines=[line for row in rows for line in row.source_lines],
        line_span=(rows[0].line_span[0], rows[-1].line_span[1]),
    )


def group_rows_by_condition(rows: list[AssembledRow]) -> list[AssembledRow]:
    """Merge adjacent rows in a region that describe the same weather aberration.

    WHY THIS IS NEEDED

    `assemble_rows` breaks a run when the anchor column falls blank, and the
    template puts blank lines *inside* a condition. On Sirsa page 7 the single
    condition "Early season drought (delayed onset) Delay by 2 weeks (July 3rd
    week)" is laid out with a blank line after "Early season", another after
    "drought", and another after "(delayed onset)" -- and the gap that separates
    two different conditions is exactly the same size as the gaps inside one. No
    amount of whitespace arithmetic can tell them apart.

    THE RULE

    Meaning can, where geometry cannot. Two adjacent rows merge when they
    normalize to the same `ConditionCode`, and a row that normalizes to
    `UNMAPPED` merges into whichever group it touches. A bare fragment like
    "Early season" or "drought" is `UNMAPPED` on its own and belongs with the
    "(delayed onset)" beside it; two rows that both say `DELAYED_ONSET` are the
    same contingency described at two levels of detail (the category and its
    "delay by N weeks" sub-row).

    The result is one rule per distinct condition code per table region, which is
    exactly the granularity the trigger engine joins at -- it looks rules up by
    `(district, condition_code)`, so two rules sharing a code in one document are
    two answers to a question that has one.

    WHAT IT COSTS

    Where a region really does hold several distinct sub-rows under one code --
    Assam's plans list separate crops for "Rainfed medium land", "Rainfed low
    land" and "Up land" under a single delayed onset -- their text is combined
    into one rule rather than kept apart. That loses granularity but no content,
    and it errs toward showing a reviewer the whole block the citation points at.
    Splitting instead would mean guessing sub-row boundaries, and a wrong guess
    puts one farming situation's crop beside another's advice.
    """
    if not rows:
        return []

    groups: list[list[AssembledRow]] = []
    group_codes: list[ConditionCode] = []

    for row in rows:
        code = normalize_condition(row.cells[0] if row.cells else "")
        if not groups:
            groups.append([row])
            group_codes.append(code)
            continue

        current = group_codes[-1]
        mergeable = (
            code is ConditionCode.UNMAPPED
            or current is ConditionCode.UNMAPPED
            or code is current
        )
        if mergeable:
            groups[-1].append(row)
            # A real code claims the group from UNMAPPED; UNMAPPED never
            # overwrites a code that has already been established.
            if current is ConditionCode.UNMAPPED:
                group_codes[-1] = code
        else:
            groups.append([row])
            group_codes.append(code)

    return [_merge_rows(group) for group in groups]


def _extract_from_tables(
    pages: list[DocumentPage], document: DocumentMetadata
) -> list[DACPRuleDraft]:
    """The geometric path: reconstruct each page's tables, then map their rows.

    Header context here means the region's own column titles, recovered by
    `tables.header_labels`. A region whose titles are unrecognizable still yields
    rows -- they are simply scored as having no header context, which is what
    routes them to review.
    """
    drafts: list[DACPRuleDraft] = []
    now = datetime.now(UTC)

    for page in pages:
        for region in find_table_regions(page.text, page=page.page):
            bands = column_bands(region.lines)
            if not bands:
                continue
            titles = header_labels(region, bands)
            field_by_column = [_match_header_field(title) for title in titles]
            had_header = any(field is not None for field in field_by_column)

            for row in group_rows_by_condition(assemble_rows(region)):
                fields = _fields_from_row(row, field_by_column, document)
                if fields is None:
                    continue

                code, matched_phrase = explain_normalization(fields.condition)
                fields = fields.model_copy(update={"condition_code": code})

                confidence, notes = score_draft(fields, had_header_context=had_header)
                notes.append(
                    f"reassembled from {len(row.source_lines)} source line(s) "
                    f"across {len(bands)} column(s)"
                )
                notes.append(
                    f"condition normalized to {code.value!r} via {matched_phrase!r}"
                    if matched_phrase
                    else "condition could not be normalized to a known code"
                )

                drafts.append(
                    DACPRuleDraft(
                        document_id=document.id,
                        fields=fields,
                        citation=Citation(
                            document=document.filename,
                            page=region.page,
                            source_text=_clip(row.source_text),
                        ),
                        confidence=confidence,
                        extractor_version=EXTRACTOR_VERSION,
                        extracted_at=now,
                        notes=notes,
                    )
                )
    return drafts


def extract_rules(
    chunks: list[Chunk],
    document: DocumentMetadata,
    *,
    pages: list[DocumentPage] | None = None,
) -> list[DACPRuleDraft]:
    """Extract rule drafts, preferring geometric table reconstruction.

    Args:
        chunks: Page-ordered chunks, used by the line-level fallback.
        document: The source document's metadata.
        pages: Page text for the geometric path. Optional so existing callers
            and tests that only have chunks keep working unchanged; when it is
            omitted, only the line-level path runs.

    Returns:
        Drafts from the geometric path when it found any table it could read,
        otherwise drafts from the line-level path.
    """
    if pages:
        table_drafts = _extract_from_tables(pages, document)
        if table_drafts:
            return table_drafts
    return _extract_from_lines(chunks, document)


def _extract_from_lines(chunks: list[Chunk], document: DocumentMetadata) -> list[DACPRuleDraft]:
    """Extract rule drafts from page-ordered chunks.

    Table header state resets at each page boundary -- a header on page 12
    never implicitly applies to a table on page 13. If DACP tables span
    pages without repeating headers, that page's rows fall back to the
    no-header-context path and are routed to review; this is a deliberate
    safety choice over guessing column alignment across a page break.

    The no-header fallback only activates once at least one real DACP
    contingency-table header has been recognized somewhere earlier in the
    document. This keeps unrelated tables in the document (district
    profile, land use, irrigation sources, etc.) from being extracted as
    noise before the contingency-measures section even starts.
    """
    drafts: list[DACPRuleDraft] = []
    now = datetime.now(UTC)

    current_page: int | None = None
    header_fields: list[str | None] | None = None
    seen_dacp_section = False

    for chunk in chunks:
        if chunk.page != current_page:
            current_page = chunk.page
            header_fields = None

        if chunk.kind is not SourceKind.TABLE_ROW or chunk.columns is None:
            continue

        if header_fields is None and _is_header_row(chunk.columns):
            header_fields = [_match_header_field(cell) for cell in chunk.columns]
            seen_dacp_section = True
            continue

        if header_fields is None and not seen_dacp_section:
            continue

        citation = Citation(document=document.filename, page=chunk.page, source_text=chunk.text)

        if header_fields is not None:
            mapped = _map_row(chunk.columns, header_fields)
            fields = DACPRuleFields(
                district=document.district,
                block=mapped.get("block"),
                farming_situation=mapped.get("farming_situation"),
                crop=mapped.get("crop"),
                soil=mapped.get("soil"),
                crop_stage=mapped.get("crop_stage"),
                condition=mapped.get("condition") or chunk.text,
                action=mapped.get("action"),
                variety=mapped.get("variety"),
                seed_rate=mapped.get("seed_rate"),
                actor=mapped.get("actor"),
            )
            confidence, notes = score_draft(fields, had_header_context=True)
        else:
            fields = DACPRuleFields(district=document.district, condition=chunk.text)
            confidence, notes = score_draft(fields, had_header_context=False)
            notes.append("no preceding header row recognized on this page")

        # Normalization runs on both branches. A fragment usually normalizes to
        # UNMAPPED, which is the honest answer -- and, being excluded from
        # EMITTABLE_CONDITION_CODES, an inert one.
        code, matched_phrase = explain_normalization(fields.condition)
        fields = fields.model_copy(update={"condition_code": code})
        notes.append(
            f"condition normalized to {code.value!r} via {matched_phrase!r}"
            if matched_phrase
            else "condition could not be normalized to a known code"
        )

        drafts.append(
            DACPRuleDraft(
                document_id=document.id,
                fields=fields,
                citation=citation,
                confidence=confidence,
                extractor_version=EXTRACTOR_VERSION,
                extracted_at=now,
                notes=notes,
            )
        )

    return drafts
