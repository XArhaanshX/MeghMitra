"""PDF -> pages, and content -> structured rule.

Covers spec invariants 1 (PDF -> pages), 3 (content -> structured rule), and
6 (missing values remain null).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ankur_schemas.document import DocumentMetadata
from ankur_schemas.enums import ExtractionMethod, SourceKind
from document_intelligence.chunker import Chunk
from document_intelligence.extractor import extract_rules
from document_intelligence.loader import load_document


def _doc(**overrides) -> DocumentMetadata:
    defaults = dict(
        filename="HAR16-Sirsa-30-06-2011.pdf",
        district="Sirsa",
        state="Haryana",
        registered_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return DocumentMetadata(**defaults)


class TestLoadDocument:
    def test_pdf_becomes_page_numbered_pages(self, sirsa_pdf_path: Path):
        document, pages = load_document(sirsa_pdf_path, district="Sirsa", state="Haryana")

        assert document.filename == sirsa_pdf_path.name
        assert document.page_count == len(pages)
        assert [p.page for p in pages] == list(range(1, len(pages) + 1))
        # every page must record how its text was obtained -- required for provenance
        assert all(p.extraction_method in ExtractionMethod for p in pages)
        # this document has a real text layer; at least one page should use it
        assert any(p.extraction_method == ExtractionMethod.NATIVE_TEXT for p in pages)


class TestExtractRules:
    def test_table_row_maps_against_recognized_header(self):
        document = _doc()
        chunks = [
            Chunk(
                document_id=document.id,
                page=12,
                text="Crop | Condition | Contingency measure | Variety | Seed Rate | Actor",
                kind=SourceKind.TABLE_ROW,
                columns=[
                    "Crop",
                    "Condition",
                    "Suggested Contingency measure",
                    "Variety",
                    "Seed Rate",
                    "Actor",
                ],
            ),
            Chunk(
                document_id=document.id,
                page=12,
                text="Pearl millet | 15-20 day dry spell | Re-sow | HHB-67 Improved | - | BAO",
                kind=SourceKind.TABLE_ROW,
                columns=[
                    "Pearl millet",
                    "15-20 day dry spell after sowing",
                    "Re-sow",
                    "HHB-67 Improved",
                    "-",
                    "BAO",
                ],
            ),
        ]

        drafts = extract_rules(chunks, document)

        assert len(drafts) == 1
        draft = drafts[0]
        assert draft.fields.crop == "Pearl millet"
        assert draft.fields.condition == "15-20 day dry spell after sowing"
        assert draft.fields.action == "Re-sow"
        assert draft.fields.variety == "HHB-67 Improved"
        assert draft.citation.page == 12
        assert draft.citation.document == document.filename
        assert draft.document_id == document.id

    def test_missing_cells_stay_null_never_guessed(self):
        """A '-' cell must map to None, not to a guessed value or an empty string."""
        document = _doc()
        chunks = [
            Chunk(
                document_id=document.id,
                page=12,
                text="Crop | Condition | Contingency measure | Variety | Seed Rate | Actor",
                kind=SourceKind.TABLE_ROW,
                columns=[
                    "Crop",
                    "Condition",
                    "Suggested Contingency measure",
                    "Variety",
                    "Seed Rate",
                    "Actor",
                ],
            ),
            Chunk(
                document_id=document.id,
                page=12,
                text="Cotton | Delayed onset 3wk | Shift short duration variety | - | - | BAO",
                kind=SourceKind.TABLE_ROW,
                columns=[
                    "Cotton",
                    "Delayed onset by 3 weeks",
                    "Shift to short duration variety",
                    "-",
                    "-",
                    "BAO",
                ],
            ),
        ]

        drafts = extract_rules(chunks, document)

        assert len(drafts) == 1
        assert drafts[0].fields.variety is None
        assert drafts[0].fields.seed_rate is None
        assert drafts[0].fields.crop == "Cotton"

    def test_rows_before_any_dacp_header_are_not_extracted(self):
        """A 2-column row in an unrelated table (e.g. land-use stats) must
        never surface as a rule -- only rows within a recognized
        contingency-measures section are candidates at all.
        """
        document = _doc()
        chunks = [
            Chunk(
                document_id=document.id,
                page=2,
                text="Net irrigated area  338",
                kind=SourceKind.TABLE_ROW,
                columns=["Net irrigated area", "338"],
            ),
        ]

        drafts = extract_rules(chunks, document)

        assert drafts == []
