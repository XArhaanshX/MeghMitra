import { describe, expect, it } from 'vitest';

import {
  conditionCodeSchema,
  dacpRuleFieldsSchema,
  dacpRuleSchema,
  reviewStatusSchema,
} from '../rule';

describe('reviewStatusSchema', () => {
  it('accepts each documented review status', () => {
    for (const status of ['pending', 'needs_review', 'approved', 'rejected']) {
      expect(reviewStatusSchema.safeParse(status).success).toBe(true);
    }
  });

  it('rejects an unknown status', () => {
    expect(reviewStatusSchema.safeParse('archived').success).toBe(false);
  });
});

describe('conditionCodeSchema', () => {
  it('accepts null for an unmapped condition', () => {
    expect(conditionCodeSchema.safeParse(null).success).toBe(true);
  });

  it('accepts a documented condition code', () => {
    expect(conditionCodeSchema.safeParse('dry_spell_after_sowing').success).toBe(true);
  });

  it('rejects an undocumented code', () => {
    expect(conditionCodeSchema.safeParse('flood').success).toBe(false);
  });
});

describe('dacpRuleFieldsSchema', () => {
  it('accepts null for every field except district and condition', () => {
    const result = dacpRuleFieldsSchema.safeParse({
      district: 'Sirsa',
      block: null,
      farming_situation: null,
      crop: null,
      soil: null,
      crop_stage: null,
      condition: 'Dry spell after sowing',
      condition_code: null,
      action: null,
      variety: null,
      seed_rate: null,
      actor: null,
    });
    expect(result.success).toBe(true);
  });

  it('requires district and condition to be present', () => {
    const result = dacpRuleFieldsSchema.safeParse({ condition_code: null });
    expect(result.success).toBe(false);
  });
});

describe('dacpRuleSchema', () => {
  it('parses a full DACPRule payload matching the documented contract', () => {
    const payload = {
      id: '550e8400-e29b-41d4-a716-446655440000',
      document_id: null,
      fields: {
        district: 'Sirsa',
        block: null,
        farming_situation: null,
        crop: 'Pearl millet',
        soil: null,
        crop_stage: 'After sowing',
        condition: 'Dry spell after sowing',
        condition_code: 'dry_spell_after_sowing',
        action: 'Re-sow',
        variety: 'HHB-67 (Improved)',
        seed_rate: null,
        actor: 'State Agriculture Department',
      },
      citation: {
        document: 'HAR16-Sirsa-30-06-2011.pdf',
        page: 9,
        source_text: null,
        bounding_region: null,
      },
      confidence: 0.94,
      extractor_version: '1.0.0',
      extracted_at: '2020-07-15T00:00:00Z',
      review_status: 'approved',
      reviewed_by: 'reviewer',
      reviewed_at: '2020-07-16T00:00:00Z',
      notes: [],
    };
    expect(dacpRuleSchema.safeParse(payload).success).toBe(true);
  });
});
