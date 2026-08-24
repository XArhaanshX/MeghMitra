import { Badge } from '@/components/ui/badge';
import type { ConditionCode } from '@/schemas';

interface ConditionCodeBadgeProps {
  code: ConditionCode;
}

const LABEL: Record<Exclude<ConditionCode, null>, string> = {
  delayed_onset: 'Delayed onset',
  dry_spell_after_sowing: 'Dry spell after sowing',
  mid_season_dry_spell: 'Mid-season dry spell',
  terminal_drought: 'Terminal drought',
  unseasonal_rain: 'Unseasonal rain',
  unmapped: 'Unmapped',
};

export function ConditionCodeBadge({ code }: ConditionCodeBadgeProps) {
  if (!code) {
    return <Badge variant="outline">Not classified</Badge>;
  }
  return <Badge variant="secondary">{LABEL[code]}</Badge>;
}
