-- Wire trigger_events / advisories to the fields the API actually stores.
-- 0001_init.sql left these as placeholders; POST /advisories was stuffing
-- block_key + reasons into payload JSONB and the action into advisories.channel.
-- Dedicated columns keep the audit log queryable without breaking existing rows.

ALTER TABLE trigger_events
    ADD COLUMN IF NOT EXISTS block_key TEXT,
    ADD COLUMN IF NOT EXISTS reasons JSONB NOT NULL DEFAULT '[]'::jsonb;

UPDATE trigger_events
SET block_key = payload ->> 'block_key'
WHERE block_key IS NULL AND payload ? 'block_key';

UPDATE trigger_events
SET reasons = COALESCE(payload -> 'reasons', '[]'::jsonb)
WHERE reasons = '[]'::jsonb AND payload ? 'reasons';

ALTER TABLE advisories
    ADD COLUMN IF NOT EXISTS action TEXT,
    ADD COLUMN IF NOT EXISTS reason TEXT;

UPDATE advisories
SET action = channel
WHERE action IS NULL
  AND channel IN ('wait', 'sow', 're_sow', 'abstain');

UPDATE advisories
SET channel = 'api'
WHERE channel IN ('wait', 'sow', 're_sow', 'abstain');

INSERT INTO schema_migrations (filename) VALUES ('0002_wire_trigger_emission.sql')
ON CONFLICT (filename) DO NOTHING;
