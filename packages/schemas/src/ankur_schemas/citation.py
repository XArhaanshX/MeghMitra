"""Provenance / citation models.

Every extracted rule must be traceable to a specific document and page.
`Citation` is the unit of proof; `Provenance` wraps it with extraction
metadata (when, by what extractor version, at what confidence).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    """Pointer back to the exact source location a rule was extracted from."""

    model_config = ConfigDict(frozen=True)

    document: str = Field(
        ..., description="Source document filename, e.g. 'HAR16-Sirsa-30-06-2011.pdf'."
    )
    page: int = Field(..., ge=1, description="1-indexed page number within the document.")
    source_text: str | None = Field(
        default=None,
        description="Verbatim snippet the rule was extracted from, if captured.",
    )
    bounding_region: str | None = Field(
        default=None,
        description="Optional layout region identifier (e.g. table cell range) on the page.",
    )


class Provenance(BaseModel):
    """Full extraction provenance for a rule: citation plus how/when it was produced."""

    model_config = ConfigDict(frozen=True)

    citation: Citation
    extracted_at: datetime
    extractor_version: str = Field(
        ..., description="Version tag of the extractor that produced this rule."
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
