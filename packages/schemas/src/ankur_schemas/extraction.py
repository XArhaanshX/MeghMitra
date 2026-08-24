"""Extraction run bookkeeping: one record per
`python -m document_intelligence.ingest` invocation.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExtractionRun(BaseModel):
    """A single execution of the extraction pipeline against one document."""

    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    extractor_version: str
    started_at: datetime
    finished_at: datetime | None = None
    pages_processed: int = 0
    rules_extracted: int = 0
    rules_needing_review: int = 0
    error: str | None = None
