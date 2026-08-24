"""OCR engine abstraction.

Kept as a narrow `Protocol` so the pipeline never hard-depends on a specific
OCR toolchain. `NullOCREngine` is the default: it makes "no OCR configured"
an explicit, recorded state (`ExtractionMethod.OCR_UNAVAILABLE`) rather than
a silent failure or a crash. `TesseractOCREngine` is provided for real use
once `pytesseract`/`pdf2image`/the `tesseract` binary are installed
(`document-intelligence[ocr]` extra).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class OCREngine(Protocol):
    def extract_page_text(self, pdf_path: Path, page_number: int) -> str:
        """Return OCR'd text for a 1-indexed page. Raise on failure."""
        ...


class OCRUnavailableError(RuntimeError):
    """Raised by `NullOCREngine` -- callers must catch this and record
    `ExtractionMethod.OCR_UNAVAILABLE` rather than letting ingestion crash.
    """


class NullOCREngine:
    """Default OCR engine: always reports unavailable.

    A page with no text layer is a normal, expected DACP scenario (scanned
    plans exist). Without a real OCR engine configured we must not invent
    text -- we record the page as requiring OCR and leave it out of rule
    extraction until a real engine is wired in.
    """

    def extract_page_text(self, pdf_path: Path, page_number: int) -> str:
        raise OCRUnavailableError(
            f"OCR required for {pdf_path.name} page {page_number}, but no OCR engine is configured"
        )


class TesseractOCREngine:
    """OCR via `pytesseract` + `pdf2image`. Requires the `ocr` extra and the
    system `tesseract` + `poppler` binaries.
    """

    def __init__(self, dpi: int = 300) -> None:
        self._dpi = dpi

    def extract_page_text(self, pdf_path: Path, page_number: int) -> str:
        try:
            import pytesseract
            from pdf2image import convert_from_path
        except ImportError as exc:  # pragma: no cover - exercised only with the ocr extra
            raise OCRUnavailableError(
                "pytesseract/pdf2image not installed; install document-intelligence[ocr]"
            ) from exc

        images = convert_from_path(
            str(pdf_path), dpi=self._dpi, first_page=page_number, last_page=page_number
        )
        if not images:  # pragma: no cover - defensive
            raise OCRUnavailableError(f"pdf2image produced no image for page {page_number}")
        return pytesseract.image_to_string(images[0])
