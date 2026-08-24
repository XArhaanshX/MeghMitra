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
  sow: 'border-emerald-500/40 bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  wait: 'border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-400',
  re_sow: 'border-primary/40 bg-primary/15 text-primary',
  abstain: 'border-border bg-muted text-muted-foreground',
};

export function ActionChip({ action }: ActionChipProps) {
  return (
    <span
      role="status"
      className={cn(
        'inline-flex items-center rounded-full border px-4 py-1.5 text-lg font-semibold tracking-wide',
        CLASS[action]
      )}
    >
      {LABEL[action]}
    </span>
  );
}
