-- Ankur initial schema.
--
-- Core tables (documents, document_pages, extracted_rules, rule_citations,
-- extraction_runs, review_queue) back the DACP extraction pipeline. The
-- future tables at the bottom are deliberately minimal placeholders for the
-- weather trigger engine described in the README; they are NOT wired to any
-- code yet.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Documents
-- ---------------------------------------------------------------------------

CREATE TABLE documents (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename       TEXT NOT NULL,
    district       TEXT NOT NULL,
    state          TEXT NOT NULL,
    page_count     INTEGER,
    sha256         TEXT,
    status         TEXT NOT NULL DEFAULT 'registered'
                       CHECK (status IN ('registered', 'extracting', 'extracted', 'failed')),
    registered_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX documents_sha256_idx ON documents (sha256) WHERE sha256 IS NOT NULL;
CREATE INDEX documents_district_idx ON documents (state, district);

CREATE TABLE document_pages (
    document_id        UUID NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    page               INTEGER NOT NULL CHECK (page >= 1),
    text               TEXT NOT NULL,
    extraction_method  TEXT NOT NULL
                           CHECK (extraction_method IN ('native_text', 'ocr', 'ocr_unavailable')),
    has_table          BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (document_id, page)
);

-- ---------------------------------------------------------------------------
-- Extracted rules + provenance
-- ---------------------------------------------------------------------------

-- `fields` and `citation` are stored as JSONB rather than columns-per-field:
-- DACP documents are inconsistent in what they specify (see
-- ankur_schemas.rule.DACPRuleFields), and the field set is expected to be
-- refined as real Sirsa DACP structure is inspected. `rule_citations`
-- below still gives citations first-class queryability without forcing a
-- premature column schema on `fields`.
CREATE TABLE extracted_rules (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id        UUID REFERENCES documents (id) ON DELETE SET NULL,
    fields             JSONB NOT NULL,
    citation           JSONB NOT NULL,
    confidence         REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    extractor_version  TEXT NOT NULL,
    extracted_at       TIMESTAMPTZ NOT NULL,
    review_status      TEXT NOT NULL DEFAULT 'pending'
                           CHECK (review_status IN ('pending', 'needs_review', 'approved', 'rejected')),
    reviewed_by        TEXT,
    reviewed_at        TIMESTAMPTZ,
    notes              JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Core product invariant, enforced at the database level too:
    -- an APPROVED rule must carry a citation with a document name.
    CONSTRAINT approved_rules_require_citation
        CHECK (review_status <> 'approved' OR (citation ->> 'document') IS NOT NULL)
);

CREATE INDEX extracted_rules_document_idx ON extracted_rules (document_id);
CREATE INDEX extracted_rules_review_status_idx ON extracted_rules (review_status);

-- Queryable, denormalized citation index. `extracted_rules.citation` (JSONB)
-- remains the source of truth returned by the API; this table exists so
-- "which rules cite page 37 of the Sirsa plan" is a plain indexed lookup.
CREATE TABLE rule_citations (
    rule_id      UUID NOT NULL REFERENCES extracted_rules (id) ON DELETE CASCADE,
    document     TEXT NOT NULL,
    page         INTEGER NOT NULL CHECK (page >= 1),
    source_text  TEXT,
    PRIMARY KEY (rule_id)
);

CREATE INDEX rule_citations_document_page_idx ON rule_citations (document, page);

CREATE TABLE extraction_runs (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id            UUID NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    extractor_version      TEXT NOT NULL,
    started_at             TIMESTAMPTZ NOT NULL,
    finished_at            TIMESTAMPTZ,
    pages_processed        INTEGER NOT NULL DEFAULT 0,
    rules_extracted        INTEGER NOT NULL DEFAULT 0,
    rules_needing_review   INTEGER NOT NULL DEFAULT 0,
    error                  TEXT
);

CREATE INDEX extraction_runs_document_idx ON extraction_runs (document_id);

-- Denormalized queue of rules awaiting human review. `review_status =
-- 'needs_review'` on extracted_rules is the source of truth; this table is
-- an optional worklist (assignment, priority) layered on top -- unused by
-- the bootstrap API, which reads `extracted_rules` directly, but reserved
-- so a future reviewer-assignment feature has somewhere to live.
CREATE TABLE review_queue (
    rule_id      UUID PRIMARY KEY REFERENCES extracted_rules (id) ON DELETE CASCADE,
    queued_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_to  TEXT,
    priority     SMALLINT NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- Future trigger-engine tables (placeholders only, not yet used by any code)
-- ---------------------------------------------------------------------------

CREATE TABLE blocks (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    district   TEXT NOT NULL,
    state      TEXT NOT NULL,
    name       TEXT NOT NULL,
    geom       GEOMETRY(MultiPolygon, 4326)
);

CREATE TABLE weather_observations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_id     UUID REFERENCES blocks (id),
    observed_at  TIMESTAMPTZ NOT NULL,
    rainfall_mm  REAL,
    source       TEXT
);

CREATE TABLE forecast_snapshots (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_id      UUID REFERENCES blocks (id),
    issued_at     TIMESTAMPTZ NOT NULL,
    valid_from    DATE NOT NULL,
    valid_to      DATE NOT NULL,
    payload       JSONB NOT NULL,
    source        TEXT
);

CREATE TABLE soil_data (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_id   UUID REFERENCES blocks (id),
    soil_type  TEXT,
    metadata   JSONB
);

CREATE TABLE trigger_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_id     UUID REFERENCES blocks (id),
    rule_id      UUID REFERENCES extracted_rules (id),
    detected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    condition    TEXT,
    payload      JSONB
);

CREATE TABLE advisories (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_event_id  UUID REFERENCES trigger_events (id),
    rule_id           UUID REFERENCES extracted_rules (id),
    generated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    channel           TEXT,
    delivered_to      TEXT
);

CREATE TABLE audit_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor       TEXT,
    action      TEXT NOT NULL,
    entity      TEXT,
    entity_id   UUID,
    details     JSONB
);
