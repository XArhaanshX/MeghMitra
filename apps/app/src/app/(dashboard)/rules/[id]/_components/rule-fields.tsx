import { ConditionCodeBadge } from '@/components/rules';
import { NullField } from '@/components/shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { DACPRuleFields } from '@/schemas';

interface RuleFieldsProps {
  fields: DACPRuleFields;
}

export function RuleFields({ fields }: RuleFieldsProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <CardTitle className="text-lg">Fields</CardTitle>
        <ConditionCodeBadge code={fields.condition_code} />
      </CardHeader>
      <CardContent className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
        <NullField label="District" value={fields.district} />
        <NullField label="Block" value={fields.block} />
        <NullField label="Farming situation" value={fields.farming_situation} />
        <NullField label="Soil" value={fields.soil} />
        <NullField label="Crop stage" value={fields.crop_stage} />
        <NullField label="Action" value={fields.action} />
        <NullField label="Variety" value={fields.variety} />
        <NullField label="Seed rate" value={fields.seed_rate} />
        <NullField label="Actor" value={fields.actor} />
      </CardContent>
    </Card>
  );
}
