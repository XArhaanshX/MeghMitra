"""In-memory repository implementations.

Used by unit/integration tests and by local dev without Postgres. Implements
the same `Protocol`s as the Postgres-backed repositories in `apps/api/app/db.py`,
so services and tests are storage-agnostic.
"""

from __future__ import annotations

from uuid import UUID

from ankur_schemas.advisory import Advisory, TriggerEvent
from ankur_schemas.document import DocumentMetadata, DocumentPage
from ankur_schemas.enums import DocumentStatus
from ankur_schemas.extraction import ExtractionRun
from ankur_schemas.rule import DACPRule


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[UUID, DocumentMetadata] = {}
        self._pages: dict[UUID, list[DocumentPage]] = {}

    async def add(self, document: DocumentMetadata) -> DocumentMetadata:
        self._documents[document.id] = document
        self._pages.setdefault(document.id, [])
        return document

    async def get(self, document_id: UUID) -> DocumentMetadata | None:
        return self._documents.get(document_id)

    async def list(self) -> list[DocumentMetadata]:
        return list(self._documents.values())

    async def update_status(self, document_id: UUID, status: str) -> None:
        doc = self._documents.get(document_id)
        if doc is not None:
            self._documents[document_id] = doc.model_copy(update={"status": DocumentStatus(status)})

    async def add_pages(self, pages: list[DocumentPage]) -> None:
        for page in pages:
            self._pages.setdefault(page.document_id, []).append(page)

    async def get_pages(self, document_id: UUID) -> list[DocumentPage]:
        return list(self._pages.get(document_id, []))

    async def get_page(self, document_id: UUID, page: int) -> DocumentPage | None:
        return next((p for p in self._pages.get(document_id, []) if p.page == page), None)


class InMemoryRuleRepository:
    def __init__(self) -> None:
        self._rules: dict[UUID, DACPRule] = {}

    async def add(self, rule: DACPRule) -> DACPRule:
        self._rules[rule.id] = rule
        return rule

    async def get(self, rule_id: UUID) -> DACPRule | None:
        return self._rules.get(rule_id)

    async def list(self, *, review_status: str | None = None) -> list[DACPRule]:
        rules = list(self._rules.values())
        if review_status is not None:
            rules = [r for r in rules if r.review_status == review_status]
        return rules

    async def update(self, rule: DACPRule) -> DACPRule:
        self._rules[rule.id] = rule
        return rule


class InMemoryExtractionRunRepository:
    def __init__(self) -> None:
        self._runs: dict[UUID, ExtractionRun] = {}

    async def add(self, run: ExtractionRun) -> ExtractionRun:
        self._runs[run.id] = run
        return run

    async def get(self, run_id: UUID) -> ExtractionRun | None:
        return self._runs.get(run_id)

    async def list_for_document(self, document_id: UUID) -> list[ExtractionRun]:
        return [r for r in self._runs.values() if r.document_id == document_id]


class InMemoryTriggerEventRepository:
    def __init__(self) -> None:
        self._events: dict[UUID, TriggerEvent] = {}

    async def add(self, event: TriggerEvent) -> TriggerEvent:
        self._events[event.id] = event
        return event

    async def get(self, event_id: UUID) -> TriggerEvent | None:
        return self._events.get(event_id)

    async def list(self) -> list[TriggerEvent]:
        return sorted(self._events.values(), key=lambda e: e.detected_at, reverse=True)


class InMemoryAdvisoryRepository:
    def __init__(self) -> None:
        self._advisories: dict[UUID, Advisory] = {}

    async def add(self, advisory: Advisory) -> Advisory:
        self._advisories[advisory.id] = advisory
        return advisory

    async def get(self, advisory_id: UUID) -> Advisory | None:
        return self._advisories.get(advisory_id)

    async def list(self) -> list[Advisory]:
        return sorted(self._advisories.values(), key=lambda a: a.generated_at, reverse=True)
