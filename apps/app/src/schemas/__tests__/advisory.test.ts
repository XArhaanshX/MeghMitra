import { describe, expect, it } from 'vitest';

import { advisoryActionSchema, evaluateRequestSchema, evaluateResponseSchema } from '../advisory';

const DRY_SPELL_BODY = {
  district: 'Sirsa',
  crop_already_sown: true,
  moisture: {
    block_id: 'sirsa-block-1',
    as_of: '2020-07-15',
    soil_moisture_fraction: 0.2,
    consecutive_dry_days: 10,
    days_since_sowing: 10,
    onset_delay_days: null,
    rain_3d_mm: 0,
    rain_3d_normal_mm: 10,
  },
  forecast: {
    block_id: 'sirsa-block-1',
    issued_on: '2020-07-15',
    lead_days: 14,
    probability: 0.8,
    climatological_rate: 0.2,
    model_version: 'trigger-engine/0.1.0',
  },
};

describe('advisoryActionSchema', () => {
  it('accepts all four documented actions, including abstain', () => {
    for (const action of ['sow', 'wait', 're_sow', 'abstain']) {
      expect(advisoryActionSchema.safeParse(action).success).toBe(true);
    }
  });
});

describe('evaluateRequestSchema', () => {
  it('parses the documented flagship dry-spell body', () => {
    expect(evaluateRequestSchema.safeParse(DRY_SPELL_BODY).success).toBe(true);
  });

  it('rejects a cost_loss_ratio outside the open interval (0, 1)', () => {
    const result = evaluateRequestSchema.safeParse({ ...DRY_SPELL_BODY, cost_loss_ratio: 1 });
    expect(result.success).toBe(false);
  });

  it('allows a null days_since_sowing when the crop is not yet sown', () => {
    const result = evaluateRequestSchema.safeParse({
      ...DRY_SPELL_BODY,
      crop_already_sown: false,
      moisture: { ...DRY_SPELL_BODY.moisture, days_since_sowing: null },
    });
    expect(result.success).toBe(true);
  });
});

describe('evaluateResponseSchema', () => {
  it('treats abstain as a valid, successful response with no rule or citation', () => {
    const response = {
      action: 'abstain',
      detected_condition: null,
      abstain_reasons: ['no condition detected'],
      decision_reason: null,
      threshold: null,
      probability: 0.1,
      rule: null,
      citation: null,
      trigger_event_id: '550e8400-e29b-41d4-a716-446655440000',
    };
    expect(evaluateResponseSchema.safeParse(response).success).toBe(true);
  });
});
