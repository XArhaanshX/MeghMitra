"""Wires the `document_intelligence` pipeline to persistence.

Lives in `apps/api` (not `document_intelligence`) because it's an
infrastructure concern: running the pure extraction pipeline and then
writing the results through repositories. Keeping this out of
`document_intelligence` keeps that package deployable/testable without a
database.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ankur_domain.repositories import ExtractionRunRepository
from ankur_domain.services import DocumentService, RuleService
from ankur_schemas.document import DocumentMetadata
from ankur_schemas.extraction import ExtractionRun
from ankur_schemas.rule import DACPRule
from document_intelligence.pipeline import run_ingestion


@dataclass(slots=True)
class IngestionService:
    documents: DocumentService
    rules: RuleService
    runs: ExtractionRunRepository

    async def ingest_pdf(
        self, pdf_path: Path, *, district: str, state: str
    ) -> tuple[DocumentMetadata, list[DACPRule], ExtractionRun]:
        result = run_ingestion(pdf_path, district=district, state=state)
        document = await self.documents.register(result.document)
        rules = await self.rules.record_extracted(result.rules)
        run = await self.runs.add(result.run)
        return document, rules, run
