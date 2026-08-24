"""End-to-end ingestion orchestration: PDF -> pages -> chunks -> rules.

```
PDF -> DocumentMetadata + DocumentPage[] -> Chunk[] -> DACPRuleDraft[] -> DACPRule[]
```

Each stage is independently testable (`loader`, `chunker`, `extractor`,
`validator`); `run_ingestion` just wires them together and records an
`ExtractionRun`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ankur_schemas.document import DocumentMetadata, DocumentPage
from ankur_schemas.enums import ReviewStatus
from ankur_schemas.extraction import ExtractionRun
from ankur_schemas.rule import DACPRule

from document_intelligence.chunker import chunk_pages
from document_intelligence.extractor import EXTRACTOR_VERSION, extract_rules
from document_intelligence.loader import load_document
from document_intelligence.ocr import NullOCREngine, OCREngine
from document_intelligence.validator import validate_drafts


@dataclass(frozen=True, slots=True)
class IngestionResult:
    document: DocumentMetadata
    pages: list[DocumentPage]
    rules: list[DACPRule]
    run: ExtractionRun


def run_ingestion(
    pdf_path: Path,
    *,
    district: str,
    state: str,
    ocr_engine: OCREngine | None = None,
) -> IngestionResult:
    started_at = datetime.now(UTC)
    ocr_engine = ocr_engine or NullOCREngine()

    document, pages = load_document(pdf_path, district=district, state=state, ocr_engine=ocr_engine)
    chunks = chunk_pages(pages)
    drafts = extract_rules(chunks, document)
    rules = validate_drafts(drafts)

    run = ExtractionRun(
        document_id=document.id,
        extractor_version=EXTRACTOR_VERSION,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        pages_processed=len(pages),
        rules_extracted=len(rules),
        rules_needing_review=sum(1 for r in rules if r.review_status == ReviewStatus.NEEDS_REVIEW),
    )

    return IngestionResult(document=document, pages=pages, rules=rules, run=run)
