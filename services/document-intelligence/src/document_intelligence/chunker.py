"""Page text -> page-aware chunks.

DACP plans are mostly wide contingency tables with occasional heading rows
("Rainfall situation: Delayed onset...") between sections. This module does
line-level classification only -- it never merges lines across pages and
never merges unrelated rows, so a downstream extraction bug can't silently
combine two different rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from ankur_schemas.document import DocumentPage
from ankur_schemas.enums import SourceKind

_TABLE_DELIMITERS = ("|", "\t")
_MULTI_SPACE = re.compile(r" {2,}")
_HEADING_RE = re.compile(r"^[A-Z0-9][A-Z0-9 ,/\-()&.]{3,80}:?$")


@dataclass(frozen=True, slots=True)
class Chunk:
    document_id: UUID
    page: int
    text: str
    kind: SourceKind
    columns: list[str] | None = None
    """Populated only for TABLE_ROW chunks: the row split into cells."""


def _split_row(line: str) -> list[str] | None:
    for delim in _TABLE_DELIMITERS:
        if delim in line:
            cells = [c.strip() for c in line.split(delim)]
            cells = [c for c in cells if c != ""]
            if len(cells) >= 2:
                return cells
    if _MULTI_SPACE.search(line):
        cells = [c.strip() for c in _MULTI_SPACE.split(line) if c.strip()]
        if len(cells) >= 2:
            return cells
    return None


def _classify_line(line: str) -> tuple[SourceKind, list[str] | None]:
    stripped = line.strip()
    if not stripped:
        return SourceKind.UNKNOWN, None

    columns = _split_row(stripped)
    if columns is not None:
        return SourceKind.TABLE_ROW, columns

    if _HEADING_RE.match(stripped) and len(stripped.split()) <= 12:
        return SourceKind.HEADING, None

    return SourceKind.PARAGRAPH, None


def chunk_page(page: DocumentPage) -> list[Chunk]:
    """Split one page's text into line-level chunks, each tagged with a
    `SourceKind`. Blank lines are dropped.
    """
    chunks: list[Chunk] = []
    for raw_line in page.text.splitlines():
        kind, columns = _classify_line(raw_line)
        if kind is SourceKind.UNKNOWN:
            continue
        chunks.append(
            Chunk(
                document_id=page.document_id,
                page=page.page,
                text=raw_line.strip(),
                kind=kind,
                columns=columns,
            )
        )
    return chunks


def chunk_pages(pages: list[DocumentPage]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        chunks.extend(chunk_page(page))
    return chunks
