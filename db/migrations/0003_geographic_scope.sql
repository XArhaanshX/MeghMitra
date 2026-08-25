-- Add geographic scope columns to the tables that carry rows across many
-- states/districts, so "give me rules/events/advisories for state X" is a
-- plain indexed lookup instead of a full scan (or a JSONB path query, for
-- `extracted_rules.fields`).
--
-- `documents` already has (state, district) as NOT NULL text columns
-- (0001_init.sql) with its own index (`documents_district_idx`); it is NOT
-- touched here.
--
-- `state_code`/`district_code` are the same free-text values `documents`
-- and `DACPRuleFields` already use (e.g. "Haryana" / "Sirsa"), not ISO
-- 3166-2:IN codes -- denormalized copies, not a new identity scheme.
--
-- This migration is purely additive: nullable columns only, no DROP, no
-- SET NOT NULL, and `approved_rules_require_citation` is untouched.

-- ---------------------------------------------------------------------------
-- extracted_rules -- backfilled from the owning document, going forward
-- populated directly by PostgresRuleRepository.add() from rule.fields.
-- ---------------------------------------------------------------------------

ALTER TABLE extracted_rules
    ADD COLUMN IF NOT EXISTS state_code TEXT,
    ADD COLUMN IF NOT EXISTS district_code TEXT;

UPDATE extracted_rules er
SET state_code = d.state,
    district_code = d.district
FROM documents d
WHERE er.document_id = d.id
  AND er.state_code IS NULL;

CREATE INDEX IF NOT EXISTS extracted_rules_state_district_review_idx
    ON extracted_rules (state_code, district_code, review_status);

-- ---------------------------------------------------------------------------
-- trigger_events -- no existing row has a queryable state/district value to
-- backfill from (district lives inside the `payload` JSONB, not a column),
-- so existing rows are left NULL. Going forward, PostgresTriggerEventRepository
-- .add() populates both from `TriggerEvent.payload["state"]`/["district"]
-- (set by AdvisoryEmissionService.evaluate()).
-- ---------------------------------------------------------------------------

ALTER TABLE trigger_events
    ADD COLUMN IF NOT EXISTS state_code TEXT,
    ADD COLUMN IF NOT EXISTS district_code TEXT;

CREATE INDEX IF NOT EXISTS trigger_events_state_district_detected_idx
    ON trigger_events (state_code, district_code, detected_at DESC);

-- ---------------------------------------------------------------------------
-- advisories -- `Advisory` carries no district/state of its own, only a
-- `trigger_event_id` FK, so existing rows are left NULL too. Going forward,
-- PostgresAdvisoryRepository.add() copies state_code/district_code from the
-- parent trigger_events row at insert time (it is always inserted first).
-- ---------------------------------------------------------------------------

ALTER TABLE advisories
    ADD COLUMN IF NOT EXISTS state_code TEXT,
    ADD COLUMN IF NOT EXISTS district_code TEXT;

CREATE INDEX IF NOT EXISTS advisories_state_district_generated_idx
    ON advisories (state_code, district_code, generated_at DESC);

-- ---------------------------------------------------------------------------
-- blocks -- future trigger-engine block registry (0001_init.sql: "not yet
-- used by any code"). Columns added for forward compatibility only; nothing
-- writes to `blocks` today, so there is nothing to backfill or wire up.
-- ---------------------------------------------------------------------------

ALTER TABLE blocks
    ADD COLUMN IF NOT EXISTS state_code TEXT,
    ADD COLUMN IF NOT EXISTS district_code TEXT;

INSERT INTO schema_migrations (filename) VALUES ('0003_geographic_scope.sql')
ON CONFLICT (filename) DO NOTHING;
