import * as z from 'zod';

import { citationSchema } from './citation';
import { conditionCodeSchema, dacpRuleSchema } from './rule';

// The trigger engine's four possible actions. `abstain` is a first-class,
// successful outcome -- silence, not an error -- when no condition matched.
export const advisoryActionSchema = z.enum(['sow', 'wait', 're_sow', 'abstain']);
export type AdvisoryAction = z.infer<typeof advisoryActionSchema>;

// POST /advisories request body.
export const moistureInputSchema = z.object({
  block_id: z.string(),
  as_of: z.iso.date(),
  soil_moisture_fraction: z.number().min(0).max(1),
  consecutive_dry_days: z.number().int().min(0),
  days_since_sowing: z.number().int().nullable(),
  onset_delay_days: z.number().int().nullable(),
  rain_3d_mm: z.number(),
  rain_3d_normal_mm: z.number(),
});
export type MoistureInput = z.infer<typeof moistureInputSchema>;

export const forecastInputSchema = z.object({
  block_id: z.string(),
  issued_on: z.iso.date(),
  lead_days: z.number().int().min(1),
  probability: z.number().min(0).max(1),
  climatological_rate: z.number().min(0).max(1),
  model_version: z.string(),
});
export type ForecastInput = z.infer<typeof forecastInputSchema>;

// `state` is optional -- required only when `district`'s name is ingested for
// more than one state (mirrors the backend's `_resolve_state`: an ambiguous
// district without `state` returns 422 rather than guessing).
export const evaluateRequestSchema = z.object({
  district: z.string(),
  state: z.string().optional(),
  crop_already_sown: z.boolean(),
  cost_loss_ratio: z.number().gt(0).lt(1).optional(),
  moisture: moistureInputSchema,
  forecast: forecastInputSchema,
});
export type EvaluateRequest = z.infer<typeof evaluateRequestSchema>;

// POST /advisories 201 response -- the retrieve-or-abstain decision.
export const evaluateResponseSchema = z.object({
  action: advisoryActionSchema,
  detected_condition: conditionCodeSchema,
  abstain_reasons: z.array(z.string()),
  decision_reason: z.string().nullable(),
  threshold: z.number().nullable(),
  probability: z.number(),
  rule: dacpRuleSchema.nullable(),
  citation: citationSchema.nullable(),
  trigger_event_id: z.uuid(),
});
export type EvaluateResponse = z.infer<typeof evaluateResponseSchema>;

// GET /advisories item -- non-silent emissions only, `abstain` never appears here.
export const advisorySchema = z.object({
  id: z.uuid(),
  trigger_event_id: z.uuid(),
  rule_id: z.uuid().nullable(),
  generated_at: z.string(),
  action: z.enum(['sow', 'wait', 're_sow']),
  reason: z.string().nullable(),
  channel: z.string(),
  delivered_to: z.string().nullable(),
});
export type Advisory = z.infer<typeof advisorySchema>;

// GET /trigger-events item -- full audit trail, including silent ABSTAINs.
export const triggerEventSchema = z.object({
  id: z.uuid(),
  block_key: z.string(),
  rule_id: z.uuid().nullable(),
  detected_at: z.string(),
  condition: z.string().nullable(),
  reasons: z.array(z.string()),
  payload: z.record(z.string(), z.unknown()),
});
export type TriggerEvent = z.infer<typeof triggerEventSchema>;
