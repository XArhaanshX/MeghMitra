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
from ankur_schemas.advisory import Advisory, TriggerEvent
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

    async def list(
        self, *, state: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[DocumentMetadata]:
        async with self._pool.acquire() as conn:
            if state is not None:
                rows = await conn.fetch(
                    "SELECT * FROM documents WHERE state ILIKE $1 "
                    "ORDER BY registered_at DESC LIMIT $2 OFFSET $3",
                    state,
                    limit,
                    offset,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM documents ORDER BY registered_at DESC LIMIT $1 OFFSET $2",
                    limit,
                    offset,
                )
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
        return [_page_from_row(row) for row in rows]

    async def get_page(self, document_id: UUID, page: int) -> DocumentPage | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM document_pages WHERE document_id = $1 AND page = $2",
                document_id,
                page,
            )
        return None if row is None else _page_from_row(row)


def _page_from_row(row: asyncpg.Record) -> DocumentPage:
    return DocumentPage(**dict(row))


def _json_value(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _rule_from_row(row: asyncpg.Record) -> DACPRule:
    data = dict(row)
    data["fields"] = _json_value(data["fields"])
    data["citation"] = _json_value(data["citation"])
    data["notes"] = _json_value(data["notes"])
    # Denormalized, indexed copies of fields.state/fields.district for
    # querying (see db/migrations/0003_geographic_scope.sql) -- not part of
    # the `DACPRule` domain model.
    data.pop("state_code", None)
    data.pop("district_code", None)
    return DACPRule(**data)


class PostgresRuleRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def add(self, rule: DACPRule) -> DACPRule:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """
                INSERT INTO extracted_rules
                    (id, document_id, fields, citation, confidence, extractor_version,
                     extracted_at, review_status, reviewed_by, reviewed_at, notes,
                     state_code, district_code)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
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
                rule.fields.state,
                rule.fields.district,
            )
            await conn.execute(
                """
                INSERT INTO rule_citations (rule_id, document, page, source_text)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (rule_id) DO UPDATE
                    SET document = EXCLUDED.document,
                        page = EXCLUDED.page,
                        source_text = EXCLUDED.source_text
                """,
                rule.id,
                rule.citation.document,
                rule.citation.page,
                rule.citation.source_text,
            )
        return rule

    async def get(self, rule_id: UUID) -> DACPRule | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM extracted_rules WHERE id = $1", rule_id)
        return _rule_from_row(row) if row else None

    async def list(
        self,
        *,
        review_status: str | None = None,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DACPRule]:
        conditions: list[str] = []
        params: list[object] = []
        if review_status is not None:
            params.append(review_status)
            conditions.append(f"review_status = ${len(params)}")
        if state is not None:
            params.append(state)
            conditions.append(f"state_code ILIKE ${len(params)}")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        limit_idx = len(params)
        params.append(offset)
        offset_idx = len(params)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM extracted_rules {where} "
                f"ORDER BY extracted_at DESC LIMIT ${limit_idx} OFFSET ${offset_idx}",
                *params,
            )
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


def _jsonb(value: object) -> str:
    return json.dumps(value)


class PostgresTriggerEventRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def add(self, event: TriggerEvent) -> TriggerEvent:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO trigger_events
                    (id, block_id, rule_id, detected_at, condition, payload, block_key, reasons,
                     state_code, district_code)
                VALUES ($1, NULL, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                event.id,
                event.rule_id,
                event.detected_at,
                event.condition,
                _jsonb(event.payload),
                event.block_key,
                _jsonb(event.reasons),
                event.payload.get("state"),
                event.payload.get("district"),
            )
        return event

    async def get(self, event_id: UUID) -> TriggerEvent | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM trigger_events WHERE id = $1", event_id)
        return None if row is None else _trigger_event_from_row(row)

    async def list(
        self, *, state: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[TriggerEvent]:
        async with self._pool.acquire() as conn:
            if state is not None:
                rows = await conn.fetch(
                    "SELECT * FROM trigger_events WHERE state_code ILIKE $1 "
                    "ORDER BY detected_at DESC LIMIT $2 OFFSET $3",
                    state,
                    limit,
                    offset,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM trigger_events ORDER BY detected_at DESC LIMIT $1 OFFSET $2",
                    limit,
                    offset,
                )
        return [_trigger_event_from_row(row) for row in rows]


def _trigger_event_from_row(row: asyncpg.Record) -> TriggerEvent:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload = dict(payload or {})
    reasons = (
        row["reasons"]
        if "reasons" in row and row["reasons"] is not None
        else payload.pop("reasons", [])
    )
    if isinstance(reasons, str):
        reasons = json.loads(reasons)
    block_key = (
        row["block_key"]
        if "block_key" in row and row["block_key"]
        else payload.pop("block_key", "")
    )
    return TriggerEvent(
        id=row["id"],
        block_key=block_key or "",
        rule_id=row["rule_id"],
        detected_at=row["detected_at"],
        condition=row["condition"],
        reasons=list(reasons or []),
        payload=payload,
    )


class PostgresAdvisoryRepository:
    """Postgres-backed `AdvisoryRepository`. ABSTAIN never inserts here."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def add(self, advisory: Advisory) -> Advisory:
        # `state_code`/`district_code` are copied from the parent trigger_event
        # row (already inserted by the time an Advisory is created -- see
        # `AdvisoryEmissionService.evaluate`): `Advisory` itself carries no
        # geographic field to write from directly (see ankur_schemas.advisory).
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO advisories
                    (id, trigger_event_id, rule_id, generated_at, channel, delivered_to,
                     action, reason, state_code, district_code)
                SELECT $1, $2, $3, $4, $5, $6, $7, $8, te.state_code, te.district_code
                FROM trigger_events te
                WHERE te.id = $2
                """,
                advisory.id,
                advisory.trigger_event_id,
                advisory.rule_id,
                advisory.generated_at,
                advisory.channel,
                advisory.delivered_to,
                advisory.action,
                advisory.reason,
            )
        return advisory

    async def get(self, advisory_id: UUID) -> Advisory | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM advisories WHERE id = $1", advisory_id)
        return None if row is None else _advisory_from_row(row)

    async def list(self) -> list[Advisory]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM advisories ORDER BY generated_at DESC")
        return [_advisory_from_row(row) for row in rows]


def _advisory_from_row(row: asyncpg.Record) -> Advisory:
    action = row["action"] if "action" in row and row["action"] else row["channel"]
    channel = (
        row["channel"] if row["channel"] not in {"wait", "sow", "re_sow", "abstain"} else "api"
    )
    return Advisory(
        id=row["id"],
        trigger_event_id=row["trigger_event_id"],
        rule_id=row["rule_id"],
        generated_at=row["generated_at"],
        action=action or "abstain",
        reason=row["reason"] if "reason" in row else None,
        channel=channel or "api",
        delivered_to=row["delivered_to"],
    )
