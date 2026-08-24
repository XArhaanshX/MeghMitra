# Database

Single migration file so far: `db/migrations/0001_init.sql`, applied automatically on first
`docker compose up -d` (mounted read-only at `/docker-entrypoint-initdb.d`) and re-appliable via
`make migrate`.

## Core tables (used by code today)

- `documents` -- one row per ingested PDF. Unique on `sha256` (when present) to avoid
  re-registering the same file twice.
- `document_pages` -- page-numbered text + `extraction_method`
  (`native_text` / `ocr` / `ocr_unavailable`). PK is `(document_id, page)`.
- `extracted_rules` -- the persisted `DACPRule`. `fields` and `citation` are `JSONB`, not
  columns-per-field: DACP documents are inconsistent in what they specify, and the field set is
  expected to evolve as more districts' plans are inspected (see `docs/domain-model.md`
  "Extending the schema"). A `CHECK` constraint (`approved_rules_require_citation`) enforces the
  "no citation -> no approved rule" invariant at the database layer, independent of the Python
  application code.
- `rule_citations` -- denormalized `(rule_id, document, page, source_text)` for indexed
  "which rules cite page N of document X" lookups without querying JSONB.
- `extraction_runs` -- one row per `run_ingestion()` call: pages processed, rules extracted,
  rules needing review.
- `review_queue` -- reserved worklist table (assignment, priority) layered on top of
  `extracted_rules.review_status = 'needs_review'`. **Not used by the bootstrap API** (which
  reads `extracted_rules` directly for `/review-queue`) -- exists so a future
  reviewer-assignment feature has somewhere to land without a new migration.

## Future tables (placeholders, not wired to any code)

`blocks`, `weather_observations`, `forecast_snapshots`, `soil_data`, `trigger_events`,
`advisories`, `audit_logs`. Deliberately minimal (see the original bootstrap brief's "do not
over-engineer these future tables yet"). `blocks.geom` is the one PostGIS-typed column
(`GEOMETRY(MultiPolygon, 4326)`) -- confirms the `postgis` extension is live and usable once the
trigger engine needs spatial joins.

## Adding a migration

New file, `NNNN_description.sql`, next sequence number. Never edit a migration that has already
shipped (i.e. that could already be applied to someone's local Postgres volume) -- write a new
one. End the new file with a footer that registers it in `schema_migrations`, mirroring
`0001_init.sql`'s:

```sql
INSERT INTO schema_migrations (filename) VALUES ('NNNN_description.sql')
ON CONFLICT (filename) DO NOTHING;
```

`make migrate` reads `db/migrations/*.sql` in order and, for each file, skips it if its filename
is already present in `schema_migrations` -- otherwise it applies the file (with
`-v ON_ERROR_STOP=1`, so a real SQL error fails the target loudly) and the file's own footer
records it. This makes `make migrate` safe to run repeatedly, including right after
`make docker-up` (whose `docker-entrypoint-initdb.d` already auto-applied `0001_init.sql` on a
fresh volume -- `make migrate` correctly sees it as already applied and skips it).
