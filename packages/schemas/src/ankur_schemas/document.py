"""Document and page-level schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ankur_schemas.enums import DocumentStatus, ExtractionMethod


class DocumentMetadata(BaseModel):
    """A single ingested DACP source document."""

    id: UUID = Field(default_factory=uuid4)
    filename: str
    district: str
    state: str
    page_count: int | None = None
    sha256: str | None = Field(default=None, description="Content hash, for de-duplication.")
    status: DocumentStatus = DocumentStatus.REGISTERED
    registered_at: datetime


class DocumentPage(BaseModel):
    """One page of extracted content from a document. Always page-numbered."""

    document_id: UUID
    page: int = Field(..., ge=1)
    text: str
    extraction_method: ExtractionMethod
    has_table: bool = False
