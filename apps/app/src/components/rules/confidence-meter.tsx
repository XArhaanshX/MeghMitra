import { MIN_AUTO_ELIGIBLE_CONFIDENCE } from '@/constants';
import { cn } from '@/lib/utils';

interface ConfidenceMeterProps {
  confidence: number;
  variant?: 'compact' | 'full';
}

// Display only -- confidence never gates the Approve action. A human may
// approve a low-confidence rule once they've checked the source page; this
// only flags what the extractor itself considered auto-eligible.
export function ConfidenceMeter({ confidence, variant = 'compact' }: ConfidenceMeterProps) {
  const pct = Math.round(confidence * 100);
  const isLow = confidence < MIN_AUTO_ELIGIBLE_CONFIDENCE;
  const fillColor = isLow ? 'bg-salmon-ink' : 'bg-teal-deep';

  if (variant === 'full') {
    return (
      <div className="space-y-1.5" aria-label={`${pct}% confidence`}>
        <p className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">
          Extractor confidence {pct}%
        </p>
        <div className="h-3 w-full overflow-hidden rounded-full border-2 border-ink bg-sand-50">
          <div className={cn('h-full', fillColor)} style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2" aria-label={`${pct}% confidence`}>
      <div className="h-2 w-16 overflow-hidden rounded-full border border-ink bg-sand-50">
        <div className={cn('h-full', fillColor)} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-ink-soft tabular-nums">{pct}%</span>
    </div>
  );
}
