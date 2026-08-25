"""Repository interfaces (ports).

Defined as `Protocol`s so that both the Postgres-backed implementation
(`apps/api/app/db.py`) and the in-memory implementation (`ankur_domain.memory`,
used by tests and fixtures) satisfy the same contract without inheritance.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from ankur_schemas.advisory import Advisory, TriggerEvent
from ankur_schemas.document import DocumentMetadata, DocumentPage
from ankur_schemas.extraction import ExtractionRun
from ankur_schemas.rule import DACPRule


@runtime_checkable
class DocumentRepository(Protocol):
    async def add(self, document: DocumentMetadata) -> DocumentMetadata: ...
    async def get(self, document_id: UUID) -> DocumentMetadata | None: ...
    async def list(
        self, *, state: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[DocumentMetadata]: ...
    async def update_status(self, document_id: UUID, status: str) -> None: ...
    async def add_pages(self, pages: list[DocumentPage]) -> None: ...
    async def get_pages(self, document_id: UUID) -> list[DocumentPage]: ...
    async def get_page(self, document_id: UUID, page: int) -> DocumentPage | None: ...


@runtime_checkable
class RuleRepository(Protocol):
    async def add(self, rule: DACPRule) -> DACPRule: ...
    async def get(self, rule_id: UUID) -> DACPRule | None: ...
    async def list(
        self,
        *,
        review_status: str | None = None,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DACPRule]: ...
    async def update(self, rule: DACPRule) -> DACPRule: ...


@runtime_checkable
class ExtractionRunRepository(Protocol):
    async def add(self, run: ExtractionRun) -> ExtractionRun: ...
    async def get(self, run_id: UUID) -> ExtractionRun | None: ...
    async def list_for_document(self, document_id: UUID) -> list[ExtractionRun]: ...


@runtime_checkable
class TriggerEventRepository(Protocol):
    async def add(self, event: TriggerEvent) -> TriggerEvent: ...
    async def get(self, event_id: UUID) -> TriggerEvent | None: ...
    async def list(
        self, *, state: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[TriggerEvent]: ...


@runtime_checkable
class AdvisoryRepository(Protocol):
    async def add(self, advisory: Advisory) -> Advisory: ...
    async def get(self, advisory_id: UUID) -> Advisory | None: ...
    async def list(self) -> list[Advisory]: ...
