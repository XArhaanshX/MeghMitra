"""Fixed-width table reconstruction for `pdftotext -layout` output.

WHY THIS MODULE EXISTS

`chunker.py` classifies one line at a time and deliberately never merges lines
("a downstream extraction bug can't silently combine two different rules"). That
is the right default for prose. It is the wrong model for a DACP contingency
table, because a table cell in these documents routinely wraps over four or five
physical lines:

    Normal onset          Light           Pearl millet + Greengram- Satya,
    followed by 15-20     textured        Muskan, Bharpai / Mothbean:
    days dry spell        sandy soils     RMO- 40 (Intercropping
    after sowing          susceptible to  8:4/6:3)

Line-level extraction turns that single rule into four rules, each holding a
sentence fragment. Measured on the Sirsa plan: 450 "rules" from 31 pages, every
one of them needing review, none of them joinable to anything. The fragments are
not merely low quality -- `'days dry spell'` carries no district, no action and no
normalizable condition, so no amount of downstream cleverness recovers the rule.

WHAT IT DOES INSTEAD

ICAR-CRIDA publishes all ~650 DACPs from one template, and `pdftotext -layout`
preserves its column geometry. So the table is recoverable structurally, without
a model and without an LLM:

  1. `find_table_regions`  -- locate the contingency tables on a page.
  2. `column_bands`        -- find the character ranges the columns occupy, by
                              looking for the vertical whitespace corridors that
                              run unbroken down the whole region.
  3. `assemble_rows`       -- slice each line at those corridors, then stitch
                              wrapped lines back into logical rows.

Everything here is deterministic and reversible: a cell's text is the verbatim
concatenation of the source lines that produced it, so a citation still points at
text a reviewer can find on the page.

THE ROW BOUNDARY RULE

The hard part is knowing where one logical row ends. This module uses a single
structural rule, no keyword vocabulary:

    A new logical row begins where the anchor column goes from blank to non-blank.

In the DACP template the anchor column is the leftmost one -- `Condition`. A row's
condition text occupies a contiguous run of lines; the run ends when the column
falls blank again. Lines whose anchor cell is blank are continuations, and their
other cells append to the row that is already open.

This is chosen over matching known condition phrases ("early season drought",
"delay by 2 weeks") on purpose. A vocabulary would silently drop every row
phrased in a way the vocabulary did not anticipate, across 30 states that each
word their tables slightly differently, and the loss would be invisible -- the
rows would simply never appear. Whitespace geometry is a property of the
document, not of our expectations about it.

WHERE IT GIVES UP

If no whitespace corridor survives the whole region, the columns cannot be
located and `assemble_rows` returns nothing rather than guessing a split. The
caller then falls back to the existing line-level path, which routes the text to
human review. Producing no rule is recoverable; producing a rule whose action
column was misaligned into its condition column is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_GAP_WIDTH = 2
"""Character columns of unbroken whitespace needed to call something a column
separator. `pdftotext -layout` pads with at least two spaces between columns;
one space is a word break inside a cell."""

MIN_REGION_LINES = 3
"""Below this a "region" is a stray pair of aligned lines, not a table."""

MIN_COLUMNS = 3
"""A DACP contingency table has at minimum condition / crop / measure. Two
columns is far more likely to be a district-profile key-value list, which
`extractor._is_header_row` already exists to keep out of the rule base."""

MAX_REGION_LINES = 400
"""Guard against a pathological page where no terminator is ever found."""

_MULTI_SPACE = re.compile(r" {2,}")

_PAGE_NUMBER = re.compile(r"^\d{1,3}$")

HEADER_LABELS: frozenset[str] = frozenset(
    {
        # The banner and the column titles of the ICAR-CRIDA contingency table,
        # plus the fragments they break into when the title wraps. Normalized to
        # lowercase, single-spaced, before comparison.
        "condition",
        "suggested contingency measures",
        "suggested contingency",
        "contingency measures",
        "major",
        "farming",
        "situation",
        "major farming",
        "farming situation",
        "major farming situation",
        "normal crop / cropping system",
        "normal crop/cropping system",
        "crop / cropping system",
        "crop/cropping system",
        "cropping system",
        "normal crop",
        "change in crop / cropping",
        "change in crop/cropping",
        "system including variety",
        "including variety",
        "change in crop/",
        "change in crop",
        "crop management",
        "agronomic",
        "agronomic measures",
        "agronomic measures d",
        "soil nutrient &",
        "soil nutrient",
        "moisture conservation",
        "moisture conservation measures",
        "measures",
        "remarks on",
        "remarks on implementation",
        "implementation",
        "remarks",
    }
)
"""Column titles to strip out of reassembled cells.

The template wraps its column titles over several physical lines, and those
lines interleave vertically with the first data row -- "Major" sits on the row
above "Farming", which sits beside the first row's condition text. There is no
horizontal rule to separate them, so the header cannot be removed by dropping
whole lines; it has to be removed fragment by fragment.

This is a labels-only vocabulary, and that is what makes it safe. An
unrecognized label stays in its cell as visible noise; it can never remove data,
because data never equals a column title. Contrast with matching *condition*
phrases, which the module docstring rejects: there, a miss silently deletes a
rule."""


def _normalize_label(text: str) -> str:
    return " ".join(text.split()).strip().lower().rstrip(":")


def is_header_fragment(text: str) -> bool:
    """Whether a reassembled cell fragment is a column title rather than data."""
    return _normalize_label(text) in HEADER_LABELS

# Section numbering in the ICAR-CRIDA template: "2.1.1 Rainfed situation",
# "2.2 Unusual rains", "3.1 Drought". A numbered heading ends the table above it.
_SECTION_HEADING = re.compile(r"^\s*\d+(\.\d+){1,3}\s+\S")

# The banner that opens every contingency table in the template. Matched
# case-insensitively and tolerant of the trailing "Suggested Contingency
# measures" half being absent, which happens on continuation pages.
_CONDITION_BANNER = re.compile(r"^\s*condition\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TableRegion:
    """A contiguous run of physical lines believed to be one table.

    `start_line` is the index of the banner line within the page, kept so a
    caller can report where a parse came from when a region looks wrong.
    """

    page: int
    start_line: int
    lines: list[str]


@dataclass(frozen=True, slots=True)
class AssembledRow:
    """One logical table row, reassembled from wrapped physical lines.

    Attributes:
        cells: Column text, left to right. A cell is the space-joined
            concatenation of that column's fragments across the row's lines.
        source_lines: The verbatim physical lines this row was built from. The
            citation snippet comes from here, so it stays quotable against the
            page.
        line_span: (first, last) line index within the region, for diagnostics.
    """

    cells: list[str]
    source_lines: list[str]
    line_span: tuple[int, int]

    @property
    def source_text(self) -> str:
        """The row as it appeared on the page, newlines collapsed to spaces."""
        return " ".join(" ".join(line.split()) for line in self.source_lines).strip()


def _is_tabular(line: str) -> bool:
    """Whether a line looks like it participates in a column layout.

    A line with no run of two or more spaces is full-width prose -- a note under
    the table, a paragraph, a page header. Such lines are excluded from the
    corridor computation, because a single one of them spans every column and
    would erase all the separators.
    """
    stripped = line.rstrip()
    return bool(stripped) and _MULTI_SPACE.search(stripped) is not None


def find_table_regions(page_text: str, *, page: int) -> list[TableRegion]:
    """Locate contingency-table regions on one page.

    A region opens at a `Condition` banner and closes at whichever comes first:
    the next banner, a numbered section heading, or the end of the page. Blank
    lines do NOT close a region -- the template puts blank lines *inside* tables,
    between the wrapped header and the body.

    Args:
        page_text: One page of `pdftotext -layout` output.
        page: 1-based page number, carried through for citations.

    Returns:
        Regions in page order. Empty when the page holds no contingency table,
        which is the common case: most of a DACP is district profile.
    """
    lines = page_text.splitlines()
    starts = [i for i, line in enumerate(lines) if _CONDITION_BANNER.match(line)]
    if not starts:
        return []

    regions: list[TableRegion] = []
    for position, start in enumerate(starts):
        limit = starts[position + 1] if position + 1 < len(starts) else len(lines)
        end = limit
        for index in range(start + 1, limit):
            if _SECTION_HEADING.match(lines[index]):
                end = index
                break
        end = min(end, start + MAX_REGION_LINES)
        block = lines[start:end]
        if len(block) >= MIN_REGION_LINES:
            regions.append(TableRegion(page=page, start_line=start, lines=block))
    return regions


def column_bands(lines: list[str]) -> list[tuple[int, int]]:
    """Find the character ranges the columns occupy.

    Builds an occupancy profile over character positions -- how many lines have a
    non-space character there -- and reads the columns off the zero-occupancy
    corridors that run the full height of the region.

    Only lines that pass `_is_tabular` contribute. One paragraph line spanning the
    page would otherwise fill every position and collapse the table into a single
    column.

    Args:
        lines: The region's physical lines.

    Returns:
        `(start, end)` character offsets, end-exclusive, left to right. Empty when
        fewer than `MIN_COLUMNS` columns are found, which is the module's way of
        saying "this is not a table I can read" -- see the docstring's
        "where it gives up".
    """
    tabular = [line.rstrip() for line in lines if _is_tabular(line)]
    if len(tabular) < MIN_REGION_LINES:
        return []

    width = max(len(line) for line in tabular)
    occupied = bytearray(width)
    for line in tabular:
        for index, char in enumerate(line):
            if char != " ":
                occupied[index] = 1

    bands: list[tuple[int, int]] = []
    index = 0
    while index < width:
        if occupied[index]:
            start = index
            while index < width and occupied[index]:
                index += 1
            end = index
            # Absorb a gap narrower than a column separator: it is a word break
            # inside one cell, not a boundary between two.
            while index < width:
                gap_start = index
                while index < width and not occupied[index]:
                    index += 1
                if index - gap_start >= MIN_GAP_WIDTH or index >= width:
                    index = gap_start
                    break
                while index < width and occupied[index]:
                    index += 1
                end = index
            bands.append((start, end))
        else:
            index += 1

    return bands if len(bands) >= MIN_COLUMNS else []


def _slice_cells(line: str, bands: list[tuple[int, int]]) -> list[str]:
    """Cut one physical line into per-column text at the band *boundaries*.

    Each cell runs from its own band start to the *next band's start*, not to its
    own band end, and the last cell runs to end-of-line. Slicing at band extents
    instead would silently truncate: a band's measured width comes only from the
    lines that participate in the corridor computation, so a line excluded by
    `_is_tabular` can be wider than the band it falls in. That is not
    hypothetical -- the Sirsa plan's `Early season drought` sits alone on its
    line, contributes no corridor, and loses its last three characters
    ("...drou") when cut at the band end.

    Slicing at boundaries cannot lose text, because the boundaries tile the line
    end to end.
    """
    cells: list[str] = []
    for position, (start, _end) in enumerate(bands):
        stop = len(line) if position == len(bands) - 1 else bands[position + 1][0]
        cells.append(line[start:stop].strip() if start < len(line) else "")
    return cells


def header_labels(region: TableRegion, bands: list[tuple[int, int]]) -> list[str]:
    """Reassemble each column's title from the fragments scattered down the region.

    `assemble_rows` throws header fragments away; the extractor needs them back,
    because which field a column carries is decided by what the column is called.
    Collected from *every* line rather than only from all-header lines: the
    template wraps "Major / Farming / situation" down three lines, and the second
    and third of those sit beside live data, so a whole-line test would recover
    only the word "Major" and match nothing.

    Args:
        region: The region the titles belong to.
        bands: Its column bands, from `column_bands`.

    Returns:
        One title per band, in column order, possibly empty where a column's
        title used wording `HEADER_LABELS` does not know.
    """
    parts: list[list[str]] = [[] for _ in bands]
    for line in region.lines:
        if not line.strip():
            continue
        for index, cell in enumerate(_slice_cells(line, bands)):
            if cell and is_header_fragment(cell) and cell not in parts[index]:
                parts[index].append(cell)
    return [" ".join(part) for part in parts]


def assemble_rows(region: TableRegion, *, anchor_column: int = 0) -> list[AssembledRow]:
    """Stitch a region's wrapped physical lines into logical rows.

    Applies the row-boundary rule from the module docstring: a blank-to-non-blank
    transition in `anchor_column` opens a new row; every other line appends to the
    row already open.

    Args:
        region: A region from `find_table_regions`.
        anchor_column: Index of the column that delimits rows. 0 -- the
            `Condition` column -- for the DACP template. Exposed because the rule
            is general even though the template is not.

    Column titles are stripped fragment by fragment via `is_header_fragment`, and
    a row whose anchor cell ends up empty (or holding nothing but a page number)
    is dropped -- it was the table's header banner, not a contingency.

    Returns:
        Logical rows in page order. Empty when `column_bands` could not locate the
        columns, or when no line ever opens a row.
    """
    bands = column_bands(region.lines)
    if not bands or anchor_column >= len(bands):
        return []

    rows: list[AssembledRow] = []
    open_cells: list[list[str]] | None = None
    open_lines: list[str] = []
    open_start = 0
    previous_anchor_filled = False

    def close() -> None:
        nonlocal open_cells, open_lines
        if open_cells is None:
            return
        merged = [
            " ".join(" ".join(part.split()) for part in cell if part).strip()
            for cell in open_cells
        ]
        anchor = merged[anchor_column]
        # A row is kept only if its anchor still says something after the column
        # titles are removed. What this drops is the banner block at the top of
        # every region, whose anchor cell is the word "Condition" and nothing
        # else, and the stray page-number band at the right margin.
        if anchor and not _PAGE_NUMBER.match(anchor):
            rows.append(
                AssembledRow(
                    cells=merged,
                    source_lines=list(open_lines),
                    line_span=(open_start, open_start + len(open_lines) - 1),
                )
            )
        open_cells = None
        open_lines = []

    for offset, line in enumerate(region.lines):
        if not line.strip():
            # A blank line breaks the anchor run, so the next filled anchor cell
            # opens a fresh row. It does not by itself close the open row: the
            # template puts blank lines between a row's wrapped lines.
            previous_anchor_filled = False
            continue

        cells = _slice_cells(line, bands)
        # Header fragments are removed before the anchor is tested, so a wrapped
        # column title sitting in the anchor column cannot open a spurious row.
        data_cells = ["" if is_header_fragment(cell) else cell for cell in cells]

        if any(cells) and not any(data_cells):
            # A line made entirely of column titles. Skipped *invisibly* -- it
            # does not reset the anchor run and contributes no text. Treating it
            # as blank instead would split a condition in three, because the
            # template wraps its header down through the first rows: "Mid season
            # drought" / <header line> / "(long dry spell," / <header line> /
            # "consecutive 2 weeks" is one condition interrupted twice.
            continue

        anchor_filled = bool(data_cells[anchor_column])

        if anchor_filled and not previous_anchor_filled:
            close()
            open_cells = [[] for _ in bands]
            open_start = offset

        previous_anchor_filled = anchor_filled

        if open_cells is None:
            # Content above the first row -- the wrapped table header. Dropped:
            # the header names columns, it does not describe a contingency.
            continue

        for index, cell in enumerate(data_cells):
            if cell:
                open_cells[index].append(cell)
        open_lines.append(line)

    close()
    return rows
