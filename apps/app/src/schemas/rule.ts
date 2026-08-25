import * as z from 'zod';

import { citationSchema } from './citation';

// Mirrors ankur_schemas.enums.ReviewStatus 1:1 -- keep values in sync with the backend.
export const reviewStatusSchema = z.enum(['pending', 'needs_review', 'approved', 'rejected']);
export type ReviewStatus = z.infer<typeof reviewStatusSchema>;

// The closed vocabulary of detected weather conditions a rule can match.
// `null` means the extractor didn't map the condition prose to a known code.
export const conditionCodeSchema = z
  .enum([
    'delayed_onset',
    'dry_spell_after_sowing',
    'mid_season_dry_spell',
    'terminal_drought',
    'unseasonal_rain',
    'unmapped',
  ])
  .nullable();
export type ConditionCode = z.infer<typeof conditionCodeSchema>;

// Mirrors ankur_schemas.rule.DACPRuleFields. `state`/`district`/`condition` are
// required (the backend added `state` alongside `district` to fix a real bug:
// district names repeat across states, e.g. Bijapur exists in both Karnataka
// and Chhattisgarh -- state is required for that lookup to be unambiguous).
// Every other field is nullable by design -- `null` means the DACP document
// didn't specify it, not that extraction failed. Never default/guess a value here.
export const dacpRuleFieldsSchema = z.object({
  state: z.string(),
  district: z.string(),
  block: z.string().nullable(),
  farming_situation: z.string().nullable(),
  crop: z.string().nullable(),
  soil: z.string().nullable(),
  crop_stage: z.string().nullable(),
  condition: z.string(),
  condition_code: conditionCodeSchema,
  action: z.string().nullable(),
  variety: z.string().nullable(),
  seed_rate: z.string().nullable(),
  actor: z.string().nullable(),
});
export type DACPRuleFields = z.infer<typeof dacpRuleFieldsSchema>;

// Mirrors ankur_schemas.rule.DACPRule -- the persisted, identified rule returned by
// GET /rules, GET /rules/{id}, GET /review-queue, and the approve/reject mutations.
export const dacpRuleSchema = z.object({
  id: z.uuid(),
  document_id: z.uuid().nullable(),
  fields: dacpRuleFieldsSchema,
  citation: citationSchema,
  confidence: z.number().min(0).max(1),
  extractor_version: z.string(),
  extracted_at: z.string(),
  review_status: reviewStatusSchema,
  reviewed_by: z.string().nullable(),
  reviewed_at: z.string().nullable(),
  notes: z.array(z.string()),
});
export type DACPRule = z.infer<typeof dacpRuleSchema>;
