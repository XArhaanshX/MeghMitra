"""Postgres-backed repository implementations.

Deliberately raw SQL via `asyncpg` -- no ORM. The schema is small and
inspectable (see `db/migrations/0001_init.sql`); an ORM would add
abstraction the project doesn't need yet. Each class satisfies the
corresponding `Protocol` in `ankur_domain.repositories` structurally (no
inheritance needed).
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg
from ankur_schemas.document import DocumentMetadata, DocumentPage
from ankur_schemas.extraction import ExtractionRun
from ankur_schemas.rule import DACPRule


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)


class PostgresDocumentRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def add(self, document: DocumentMetadata) -> DocumentMetadata:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents
                    (id, filename, district, state, page_count, sha256, status, registered_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                document.id,
                document.filename,
                document.district,
                document.state,
                document.page_count,
                document.sha256,
                document.status.value,
                document.registered_at,
            )
        return document

    async def get(self, document_id: UUID) -> DocumentMetadata | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM documents WHERE id = $1", document_id)
        return DocumentMetadata(**dict(row)) if row else None

    async def list(self) -> list[DocumentMetadata]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM documents ORDER BY registered_at DESC")
        return [DocumentMetadata(**dict(row)) for row in rows]

    async def update_status(self, document_id: UUID, status: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE documents SET status = $2 WHERE id = $1", document_id, status
            )

    async def add_pages(self, pages: list[DocumentPage]) -> None:
        if not pages:
            return
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO document_pages (document_id, page, text, extraction_method, has_table)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (document_id, page) DO UPDATE
                    SET text = EXCLUDED.text,
                        extraction_method = EXCLUDED.extraction_method,
                        has_table = EXCLUDED.has_table
                """,
                [
                    (p.document_id, p.page, p.text, p.extraction_method.value, p.has_table)
                    for p in pages
                ],
            )

    async def get_pages(self, document_id: UUID) -> list[DocumentPage]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM document_pages WHERE document_id = $1 ORDER BY page", document_id
            )
        return [DocumentPage(**dict(row)) for row in rows]


def _rule_from_row(row: asyncpg.Record) -> DACPRule:
    data = dict(row)
    data["fields"] = json.loads(data["fields"])
    data["citation"] = json.loads(data["citation"])
    data["notes"] = json.loads(data["notes"])
    return DACPRule(**data)


class PostgresRuleRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def add(self, rule: DACPRule) -> DACPRule:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO extracted_rules
                    (id, document_id, fields, citation, confidence, extractor_version,
                     extracted_at, review_status, reviewed_by, reviewed_at, notes)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                rule.id,
                rule.document_id,
                rule.fields.model_dump_json(),
                rule.citation.model_dump_json(),
                rule.confidence,
                rule.extractor_version,
                rule.extracted_at,
                rule.review_status.value,
                rule.reviewed_by,
                rule.reviewed_at,
                json.dumps(rule.notes),
            )
        return rule

    async def get(self, rule_id: UUID) -> DACPRule | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM extracted_rules WHERE id = $1", rule_id)
        return _rule_from_row(row) if row else None

    async def list(self, *, review_status: str | None = None) -> list[DACPRule]:
        async with self._pool.acquire() as conn:
            if review_status is not None:
                rows = await conn.fetch(
                    "SELECT * FROM extracted_rules WHERE review_status = $1 "
                    "ORDER BY extracted_at DESC",
                    review_status,
                )
            else:
                rows = await conn.fetch("SELECT * FROM extracted_rules ORDER BY extracted_at DESC")
        return [_rule_from_row(row) for row in rows]

    async def update(self, rule: DACPRule) -> DACPRule:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE extracted_rules
                SET review_status = $2, reviewed_by = $3, reviewed_at = $4, notes = $5
                WHERE id = $1
                """,
                rule.id,
                rule.review_status.value,
                rule.reviewed_by,
                rule.reviewed_at,
                json.dumps(rule.notes),
            )
        return rule


class PostgresExtractionRunRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def add(self, run: ExtractionRun) -> ExtractionRun:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO extraction_runs
                    (id, document_id, extractor_version, started_at, finished_at,
                     pages_processed, rules_extracted, rules_needing_review, error)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                run.id,
                run.document_id,
                run.extractor_version,
                run.started_at,
                run.finished_at,
                run.pages_processed,
                run.rules_extracted,
                run.rules_needing_review,
                run.error,
            )
        return run

    async def get(self, run_id: UUID) -> ExtractionRun | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM extraction_runs WHERE id = $1", run_id)
        return ExtractionRun(**dict(row)) if row else None

    async def list_for_document(self, document_id: UUID) -> list[ExtractionRun]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM extraction_runs WHERE document_id = $1 ORDER BY started_at DESC",
                document_id,
            )
        return [ExtractionRun(**dict(row)) for row in rows]
