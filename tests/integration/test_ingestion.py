"""End-to-end: real Sirsa PDF -> pages -> chunks -> rules -> ExtractionRun.

Covers spec invariant 2 (page -> extracted content) as part of the full
pipeline, using the actual Sirsa DACP PDF committed at data/raw/.
"""

from __future__ import annotations

from pathlib import Path

from ankur_schemas.enums import ReviewStatus
from document_intelligence.chunker import chunk_page
from document_intelligence.loader import load_document
from document_intelligence.pipeline import run_ingestion


def test_page_text_becomes_classified_chunks(sirsa_pdf_path: Path):
    document, pages = load_document(sirsa_pdf_path, district="Sirsa", state="Haryana")
    contingency_page = next(p for p in pages if "Condition" in p.text and "Contingency" in p.text)

    chunks = chunk_page(contingency_page)

    assert chunks, "expected at least one classified chunk on the contingency table page"
    assert all(c.page == contingency_page.page for c in chunks)
    assert all(c.document_id == document.id for c in chunks)


def test_run_ingestion_produces_cited_rules_pending_review(sirsa_pdf_path: Path):
    result = run_ingestion(sirsa_pdf_path, district="Sirsa", state="Haryana")

    assert result.run.pages_processed == result.document.page_count
    assert result.run.rules_extracted == len(result.rules)
    assert len(result.rules) > 0, (
        "expected the real Sirsa contingency tables to yield candidate rules"
    )

    for rule in result.rules:
        # every extracted rule must cite the source document and a real page
        assert rule.citation.document == sirsa_pdf_path.name
        assert 1 <= rule.citation.page <= result.document.page_count
        # extraction alone must never mark a rule approved
        assert rule.review_status in (ReviewStatus.PENDING, ReviewStatus.NEEDS_REVIEW)
