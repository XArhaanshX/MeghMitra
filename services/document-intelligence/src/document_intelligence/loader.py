"""PDF -> DocumentMetadata + page-aware DocumentPage list.

Text extraction prefers the system `pdftotext` (poppler-utils) with
`-layout`, falling back to `pypdf` when the binary isn't installed.

This is not a stylistic choice: real DACP PDFs (e.g. the Sirsa plan) embed
fonts with custom encodings that `pypdf`'s text layer decodes incorrectly --
it inserts a spurious 'H' in place of most spaces/ligatures. `pdftotext`
decodes the same document correctly and `-layout` preserves the column
alignment DACP contingency tables depend on. `pypdf` is kept as a fallback
for portability and because it's still used for page count / metadata.

Handles both normal text PDFs and scanned PDFs (delegated to an
`OCREngine`). Never fabricates page text: a page that has no text layer and
no working OCR engine is recorded as `ExtractionMethod.OCR_UNAVAILABLE` with
empty text, not silently dropped or guessed.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from ankur_schemas.document import DocumentMetadata, DocumentPage
from ankur_schemas.enums import ExtractionMethod
from pypdf import PdfReader

from document_intelligence.ocr import NullOCREngine, OCREngine, OCRUnavailableError

MIN_NATIVE_TEXT_CHARS = 20
"""Below this many characters of native text, treat the page as scanned and
attempt OCR -- extractors sometimes return a handful of stray characters for
image-only pages."""

_PDFTOTEXT_TIMEOUT_SECONDS = 60


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pdftotext_pages(pdf_path: Path) -> list[str] | None:
    """Extract per-page text via poppler's `pdftotext -layout`.

    Returns `None` (not an exception) whenever the binary is missing or the
    call fails -- callers fall back to `pypdf` rather than crashing
    ingestion over a missing optional system dependency.
    """
    binary = shutil.which("pdftotext")
    if binary is None:
        return None
    try:
        completed = subprocess.run(
            [binary, "-layout", str(pdf_path), "-"],
            capture_output=True,
            check=True,
            timeout=_PDFTOTEXT_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    text = completed.stdout.decode("utf-8", errors="replace")
    pages = text.split("\x0c")  # pdftotext separates pages with form-feed
    if pages and pages[-1] == "":
        pages.pop()
    return pages


def load_document(
    pdf_path: Path,
    *,
    district: str,
    state: str,
    ocr_engine: OCREngine | None = None,
) -> tuple[DocumentMetadata, list[DocumentPage]]:
    """Load a PDF into page-aware, page-numbered content.

    Every returned `DocumentPage` carries the page number it came from and
    how its text was obtained -- both are required for provenance later.
    """
    ocr_engine = ocr_engine or NullOCREngine()
    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)

    layout_pages = _pdftotext_pages(pdf_path)
    use_layout = layout_pages is not None and len(layout_pages) == page_count

    document = DocumentMetadata(
        filename=pdf_path.name,
        district=district,
        state=state,
        page_count=page_count,
        sha256=_sha256(pdf_path),
        registered_at=datetime.now(UTC),
    )

    pages: list[DocumentPage] = []
    for index in range(1, page_count + 1):
        if use_layout:
            native_text = layout_pages[index - 1].strip()
        else:
            native_text = (reader.pages[index - 1].extract_text() or "").strip()

        if len(native_text) >= MIN_NATIVE_TEXT_CHARS:
            pages.append(
                DocumentPage(
                    document_id=document.id,
                    page=index,
                    text=native_text,
                    extraction_method=ExtractionMethod.NATIVE_TEXT,
                    has_table="|" in native_text or "\t" in native_text or "  " in native_text,
                )
            )
            continue

        try:
            ocr_text = ocr_engine.extract_page_text(pdf_path, index).strip()
            pages.append(
                DocumentPage(
                    document_id=document.id,
                    page=index,
                    text=ocr_text,
                    extraction_method=ExtractionMethod.OCR,
                    has_table=False,
                )
            )
        except OCRUnavailableError:
            pages.append(
                DocumentPage(
                    document_id=document.id,
                    page=index,
                    text=native_text,
                    extraction_method=ExtractionMethod.OCR_UNAVAILABLE,
                    has_table=False,
                )
            )

    return document, pages
