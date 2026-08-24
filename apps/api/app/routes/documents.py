from __future__ import annotations

from pathlib import Path
from uuid import UUID

from ankur_domain.services import DocumentNotFoundError, DocumentService, PageNotFoundError
from ankur_schemas.document import DocumentMetadata, DocumentPage
from ankur_schemas.rule import DACPRule
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_document_service, get_ingestion_service
from app.ingestion import IngestionService

router = APIRouter(tags=["documents"])


class IngestRequest(BaseModel):
    path: str
    """Server-local path to a DACP PDF, e.g. 'data/raw/HAR16-Sirsa-30-06-2011.pdf'."""
    district: str
    state: str


class IngestResponse(BaseModel):
    document: DocumentMetadata
    rules: list[DACPRule]
    rules_needing_review: int


@router.get("/documents")
async def list_documents(
    service: DocumentService = Depends(get_document_service),
) -> list[DocumentMetadata]:
    return await service.list()


@router.get("/documents/{document_id}")
async def get_document(
    document_id: UUID, service: DocumentService = Depends(get_document_service)
) -> DocumentMetadata:
    try:
        return await service.get(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc


@router.get("/documents/{document_id}/pages")
async def list_document_pages(
    document_id: UUID, service: DocumentService = Depends(get_document_service)
) -> list[DocumentPage]:
    try:
        return await service.list_pages(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc


@router.get("/documents/{document_id}/pages/{page}")
async def get_document_page(
    document_id: UUID, page: int, service: DocumentService = Depends(get_document_service)
) -> DocumentPage:
    try:
        return await service.get_page(document_id, page)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except PageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="page not found") from exc


@router.post("/documents/ingest", status_code=201)
async def ingest_document(
    body: IngestRequest, service: IngestionService = Depends(get_ingestion_service)
) -> IngestResponse:
    pdf_path = Path(body.path)
    if not pdf_path.exists():
        raise HTTPException(status_code=400, detail=f"path does not exist on server: {body.path}")

    document, rules, run = await service.ingest_pdf(
        pdf_path, district=body.district, state=body.state
    )
    return IngestResponse(
        document=document, rules=rules, rules_needing_review=run.rules_needing_review
    )
