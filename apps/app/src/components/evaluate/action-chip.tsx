import { cn } from '@/lib/utils';
import type { AdvisoryAction } from '@/schemas';

interface ActionChipProps {
  action: AdvisoryAction;
}

const LABEL: Record<AdvisoryAction, string> = {
  sow: 'SOW',
  wait: 'WAIT',
  re_sow: 'RE-SOW',
  abstain: 'ABSTAIN',
};

// abstain is silence, a successful outcome -- muted, never red/error-coloured.
const CLASS: Record<AdvisoryAction, string> = {
  sow: 'border-ink bg-moss-soft text-moss',
  wait: 'border-ink bg-teal-soft text-teal-deep',
  re_sow: 'border-ink bg-teal text-sand-50',
  abstain: 'border-ink bg-sand-100 text-ink-soft',
};

export function ActionChip({ action }: ActionChipProps) {
  return (
    // No role="status" here: the result panel is already a single polite live
    // region, and a nested one makes screen readers announce twice.
    <span
      className={cn(
        'inline-flex items-center rounded-sm border-2 px-4 py-1.5 font-mono text-lg font-bold tracking-widest uppercase',
        CLASS[action]
      )}
    >
      {LABEL[action]}
    </span>
  );
}
