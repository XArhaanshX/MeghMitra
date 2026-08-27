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

// The DACP plan's own wording is "15-20 days dry spell after sowing" -- the
// trigger engine enforces that band (previously defined but not wired up),
// so a demo weather body must fall inside [15, 20] to fire RE_SOW. 10 no
// longer matches; see services/trigger-engine/src/trigger_engine/conditions.py.
const DRY_SPELL_BODY: EvaluateRequest = {
  state: 'Haryana',
  district: 'Sirsa',
  crop_already_sown: true,
  moisture: {
    block_id: 'sirsa-block-1',
    as_of: '2020-07-15',
    soil_moisture_fraction: 0.2,
    consecutive_dry_days: 17,
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
    label: 'Dry spell after sowing',
    description:
      "Sown 10 days ago, then 17 dry days, inside the plan's stated 15 to 20 day band. An approved rule covers this, so expect a re-sow recommendation citing page 9.",
    request: DRY_SPELL_BODY,
  },
  {
    id: 'not-sown',
    label: 'Same weather, not sown',
    description:
      'Identical soil moisture, but the crop is not in the ground yet. The recommendation changes to wait, because the rule that fires depends on crop stage.',
    request: { ...DRY_SPELL_BODY, crop_already_sown: false },
  },
  {
    id: 'ordinary-weather',
    label: 'Ordinary weather',
    description:
      'Wet soil, no dry spell. No condition is detected, so the system stays silent rather than finding something to say.',
    request: {
      state: 'Haryana',
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
    label: 'Neighbouring district',
    description:
      'The same dry-spell weather, moved to Hisar, where no plan has been approved. Nothing is borrowed from Sirsa next door, so the system abstains.',
    request: {
      ...DRY_SPELL_BODY,
      state: 'Haryana',
      district: 'Hisar',
      moisture: { ...DRY_SPELL_BODY.moisture, block_id: 'hisar-block-1' },
      forecast: { ...SIRSA_FORECAST, block_id: 'hisar-block-1' },
    },
  },
  {
    id: 'delayed-onset',
    label: 'Delayed monsoon onset',
    description:
      'Onset 25 days late, past the 21-day threshold, crop not yet sown. The condition is detected and a cited rule exists, but no decision model covers this condition yet, so the system says so instead of acting.',
    request: {
      state: 'Haryana',
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
  {
    id: 'cross-state-collision-check',
    label: 'Duplicate district name',
    description:
      'Bijapur exists in both Karnataka and Chhattisgarh. Naming the state is what decides which plan is read, so a Chhattisgarh request can never be answered with Karnataka government actions.',
    request: {
      state: 'Chhattisgarh',
      district: 'Bijapur',
      crop_already_sown: true,
      moisture: {
        block_id: 'bijapur-block-1',
        as_of: '2020-08-10',
        soil_moisture_fraction: 0.2,
        consecutive_dry_days: 17,
        days_since_sowing: 10,
        onset_delay_days: null,
        rain_3d_mm: 0,
        rain_3d_normal_mm: 10,
      },
      forecast: {
        block_id: 'bijapur-block-1',
        issued_on: '2020-08-10',
        lead_days: 14,
        probability: 0.7,
        climatological_rate: 0.2,
        model_version: 'trigger-engine/0.1.0',
      },
    },
  },
];
