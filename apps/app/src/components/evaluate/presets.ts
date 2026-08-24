import type { EvaluateRequest } from '@/schemas';

import type { EvaluatePreset } from './preset-bar';

const SIRSA_FORECAST = {
  block_id: 'sirsa-block-1',
  issued_on: '2020-07-15',
  lead_days: 14,
  probability: 0.8,
  climatological_rate: 0.2,
  model_version: 'trigger-engine/0.1.0',
};

const DRY_SPELL_BODY: EvaluateRequest = {
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
  forecast: SIRSA_FORECAST,
};

// Demo presets from the flagship walkthrough: fill the JSON body shown in
// evaluate-form.tsx, never a hidden request -- judges see exactly what posts.
export const EVALUATE_PRESETS: EvaluatePreset[] = [
  {
    id: 'dry-spell-after-sowing',
    label: 'Dry spell after sowing (flagship)',
    description: 'Sown, 10 dry days, low soil moisture -> expect RE-SOW, Pearl millet, page 9.',
    request: DRY_SPELL_BODY,
  },
  {
    id: 'not-sown',
    label: 'Same weather, not sown',
    description: 'Identical moisture, crop not yet sown -> expect WAIT.',
    request: { ...DRY_SPELL_BODY, crop_already_sown: false },
  },
  {
    id: 'ordinary-weather',
    label: 'Ordinary weather',
    description: 'Wet, no dry spell -> expect ABSTAIN, "no condition detected".',
    request: {
      district: 'Sirsa',
      crop_already_sown: true,
      moisture: {
        block_id: 'sirsa-block-1',
        as_of: '2020-07-15',
        soil_moisture_fraction: 0.8,
        consecutive_dry_days: 0,
        days_since_sowing: 10,
        onset_delay_days: null,
        rain_3d_mm: 10,
        rain_3d_normal_mm: 10,
      },
      forecast: SIRSA_FORECAST,
    },
  },
  {
    id: 'other-district',
    label: 'Other district (Hisar)',
    description: 'Same dry-spell weather outside Sirsa -> expect ABSTAIN, no rule leak.',
    request: {
      ...DRY_SPELL_BODY,
      district: 'Hisar',
      moisture: { ...DRY_SPELL_BODY.moisture, block_id: 'hisar-block-1' },
      forecast: { ...SIRSA_FORECAST, block_id: 'hisar-block-1' },
    },
  },
  {
    id: 'delayed-onset',
    label: 'Delayed onset',
    description: 'Not yet sown, 25-day onset delay, otherwise mild.',
    request: {
      district: 'Sirsa',
      crop_already_sown: false,
      moisture: {
        block_id: 'sirsa-block-1',
        as_of: '2020-07-15',
        soil_moisture_fraction: 0.5,
        consecutive_dry_days: 0,
        days_since_sowing: null,
        onset_delay_days: 25,
        rain_3d_mm: 5,
        rain_3d_normal_mm: 10,
      },
      forecast: SIRSA_FORECAST,
    },
  },
];
