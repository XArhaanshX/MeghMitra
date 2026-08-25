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

## ISO 3166-2:IN state codes, not LGD codes -- and districts derived from the corpus, not a hand-authored gazetteer

`packages/geo` (`ankur_geo`) needed a stable identity for India's 36 states/UTs before the
India-wide migration could key anything on `(state, district)`. Two choices, both documented in
`packages/geo/src/ankur_geo/states.py` and `districts.py`:

- **State identity is the ISO 3166-2:IN subdivision code** (`"HR"`, not a numeric Local
  Government Directory code), even though LGD codes are the correct long-term join key for most
  government datasets. This codebase has no verified source for the real LGD numbers in this
  environment, and hardcoding fabricated ones would be exactly the guessed-not-nullable value
  `AGENTS.md` already prohibits for rule fields -- just applied to geography instead. ISO
  3166-2:IN is a public, checkable standard and stable today; `State.lgd_code` stays an explicit
  `int | None`, `None` until a real LGD extract is imported, rather than invented.
- **Districts are derived by scanning the ingested `data/processed/` corpus**
  (`ankur_geo.districts.build_district_index`), not typed in from an external gazetteer. Ankur
  only needs to resolve districts it actually has a DACP for; a hand-authored national district
  list would claim coverage the corpus doesn't have and would drift the moment a new document is
  ingested. The generated snapshot (`ankur_geo._districts_generated`, produced by
  `scripts/generate_geo_reference.py`) is committed so resolution works without the 326 MB,
  gitignored `data/processed/` directory being present at import time.

## `RuleStore` keyed on `(state, district, condition_code)`, not `(district, condition_code)`

Indexing rules on district name and condition code alone looked equivalent to including state
until the corpus went national: several district names repeat across states (Bijapur in
Karnataka and Chhattisgarh, Balrampur in Uttar Pradesh and Chhattisgarh, and five more --
`services/trigger-engine/src/trigger_engine/rulestore.py`'s module docstring names all seven).
`RuleStore.candidates()` on the old two-part key would silently return whichever state's
contingency plan happened to load first for a shared district name -- not a hypothetical, it
reproduced on the real corpus. `state` is now a required first argument to `candidates()`, and
`ankur_geo.resolve_region()` is the single reusable place every other caller (ingestion, the
API, the CLI) gets the same "refuse to guess, name the ambiguity" behavior instead of
re-implementing the two-key lookup.
