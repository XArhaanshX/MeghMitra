"""Chunks -> `DACPRuleDraft`s.

This is a deterministic, heuristic table-row extractor -- not an LLM, not a
chatbot. DACP contingency tables are read column-by-column against a small
known-header vocabulary; a table row is only mapped into a field when its
column header was actually recognized on a preceding header row of the same
page. If no header context exists, the row is preserved verbatim as the
`condition` text and routed to review rather than guessed at.

This is intentionally a first pass. The next step recommended at the end of
bootstrap is to inspect the actual Sirsa DACP PDF layout and tighten this
against its real table structure (see project README).
"""

from __future__ import annotations

from datetime import UTC, datetime

from ankur_schemas.citation import Citation
from ankur_schemas.document import DocumentMetadata
from ankur_schemas.enums import SourceKind
from ankur_schemas.rule import DACPRuleDraft, DACPRuleFields

from document_intelligence.chunker import Chunk
from document_intelligence.confidence import score_draft

EXTRACTOR_VERSION = "document-intelligence/0.1.0"

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


def extract_rules(chunks: list[Chunk], document: DocumentMetadata) -> list[DACPRuleDraft]:
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
