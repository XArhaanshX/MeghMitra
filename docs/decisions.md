# Decisions log

Short-form ADRs. Add an entry when a choice was non-obvious or trades something away
deliberately -- not for routine implementation detail (that belongs in code comments/docstrings).

## Raw SQL via `asyncpg`, not an ORM

The schema is small and expected to change shape as real DACP structure is learned (see
`docs/document-intelligence.md` "Known limitation"). An ORM's migration/model layer would add
indirection before the shape has settled. `apps/api/app/db.py` is meant to be read top to
bottom; revisit once the schema stabilizes and query complexity grows past what hand-written SQL
stays readable for.

## `fields`/`citation` as JSONB on `extracted_rules`, not columns-per-field

DACP documents are inconsistent field-to-field and district-to-district (see
`docs/domain-model.md`). Column-per-field would force a migration for every new district's
quirks. `rule_citations` exists specifically so citation lookups stay indexed despite `citation`
being JSONB on the main table.

## `pdftotext` (poppler) primary, `pypdf` fallback -- not `pypdf` alone

Discovered, not assumed: `pypdf`'s text-layer decoder mangles
`data/raw/HAR16-Sirsa-30-06-2011.pdf`'s embedded font encoding (inserts a spurious `H` character
in place of most spaces). Verified `pdftotext -layout` decodes the same file correctly and
preserves column alignment. `pypdf` is kept as a fallback for portability (no assumption that
poppler-utils is installed everywhere) and because it still supplies page count for the loader.
See `services/document-intelligence/src/document_intelligence/loader.py`.

## Extraction is header-vocabulary-matched and gated by document position, not fuzzy/LLM-based

The bootstrap brief explicitly excludes an LLM agent architecture / generic RAG for this layer.
`extractor.py` only produces a candidate row once a recognized DACP contingency-table header
(`condition` + at least one other known column) has been seen; unrelated tables earlier in a
district profile document (land use, irrigation sources, etc.) are never treated as rule
candidates, even before that gate was added they showed up as ~500 spurious low-confidence
"rules" in a real ingestion run -- gating on document position removed that class of noise
entirely rather than trying to filter it after the fact.

## Confidence blocks the *automated* advisory path, not human approval

`can_approve()` only checks citation validity, not confidence -- a human reviewer can approve a
low-confidence rule after manually verifying it against the source PDF page. What's blocked is
extraction ever presenting a low-confidence draft as merely `pending` (it's routed to
`needs_review` instead), and the trigger engine (future) only consuming `review_status ==
approved` rules regardless of the confidence they were extracted at. See
`docs/domain-model.md` and `tests/unit/test_confidence.py`.

## In-memory repositories for tests, not mocks

`ankur_domain.memory.InMemory*Repository` classes satisfy the same `Protocol`s as the Postgres
implementations in `apps/api/app/db.py` structurally (no shared base class needed). Tests get
real behavior (state actually persists across calls within a test) without a live database or a
mocking framework standing in for one.
