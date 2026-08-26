import { ConditionCodeBadge } from '@/components/rules';
import { NullField } from '@/components/shared';
import type { DACPRuleFields } from '@/schemas';

interface RuleFieldsProps {
  fields: DACPRuleFields;
}

export function RuleFields({ fields }: RuleFieldsProps) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="font-heading text-xl font-bold text-ink">Rule fields</h2>
        <ConditionCodeBadge code={fields.condition_code} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <NullField label="State" value={fields.state} />
        <NullField label="District" value={fields.district} />
        <NullField label="Block" value={fields.block} />
        <NullField label="Farming situation" value={fields.farming_situation} />
        <NullField label="Soil" value={fields.soil} />
        <NullField label="Crop stage" value={fields.crop_stage} />
        <NullField label="Action" value={fields.action} />
        <NullField label="Variety" value={fields.variety} />
        <NullField label="Seed rate" value={fields.seed_rate} />
        <NullField label="Actor" value={fields.actor} />
      </div>
    </div>
  );
}
