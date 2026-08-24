"""Enumerations shared across the Ankur domain.

Kept intentionally small. DACP documents are inconsistent, so most free-text
fields (crop, variety, actor) stay as plain strings rather than closed enums.
Only fields where a closed vocabulary is safe and useful are enumerated here.
"""

from __future__ import annotations

from enum import StrEnum


class ReviewStatus(StrEnum):
    """Lifecycle of an extracted rule on its way to becoming an approved,
    advisory-eligible fact.
    """

    PENDING = "pending"
    """Extracted, schema-valid, not yet looked at by a human."""

    NEEDS_REVIEW = "needs_review"
    """Extraction was ambiguous, low-confidence, or failed an invariant.
    Requires a human decision before it can move further."""

    APPROVED = "approved"
    """A human reviewer confirmed the rule matches the source document.
    Only APPROVED rules are eligible for automated advisory output."""

    REJECTED = "rejected"
    """A human reviewer determined the extraction was wrong or unusable."""


class ExtractionMethod(StrEnum):
    """How the text for a given page was obtained."""

    NATIVE_TEXT = "native_text"
    """Extracted directly from the PDF's text layer."""

    OCR = "ocr"
    """Extracted via OCR because the page had no usable text layer."""

    OCR_UNAVAILABLE = "ocr_unavailable"
    """Page required OCR but no OCR engine was configured/available.
    Pages in this state MUST NOT produce rules with review_status other than
    needs_review."""


class SourceKind(StrEnum):
    """What kind of source region a chunk of extracted text came from."""

    PARAGRAPH = "paragraph"
    TABLE_ROW = "table_row"
    HEADING = "heading"
    UNKNOWN = "unknown"


class DocumentStatus(StrEnum):
    """Ingestion lifecycle of a source document."""

    REGISTERED = "registered"
    """Metadata recorded, extraction not yet run."""

    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    FAILED = "failed"
