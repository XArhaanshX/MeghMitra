import { NullField } from '@/components/shared';
import type { DACPRuleFields } from '@/schemas';

interface RuleFieldsProps {
  fields: DACPRuleFields;
}

export function RuleFields({ fields }: RuleFieldsProps) {
  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h2 className="font-heading text-xl font-bold text-ink">Recorded fields</h2>
        <p className="text-sm text-ink-muted">
          Transcribed from the source plan. A field marked &ldquo;Not in source&rdquo; was left
          blank in the document and is never inferred.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <NullField label="State" value={fields.state} />
        <NullField label="District" value={fields.district} />
        <NullField label="Block" value={fields.block} />
        <NullField label="Crop" value={fields.crop} />
        <NullField label="Variety" value={fields.variety} />
        <NullField label="Seed rate" value={fields.seed_rate} />
        <NullField label="Farming situation" value={fields.farming_situation} />
        <NullField label="Soil" value={fields.soil} />
        <NullField label="Crop stage" value={fields.crop_stage} />
        <NullField label="Action" value={fields.action} />
        <NullField label="Responsible actor" value={fields.actor} />
      </div>
    </section>
  );
}
