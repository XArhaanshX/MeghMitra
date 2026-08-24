import { MIN_AUTO_ELIGIBLE_CONFIDENCE } from '@/constants';

interface ConfidenceMeterProps {
  confidence: number;
}

// Display only -- confidence never gates the Approve action. A human may
// approve a low-confidence rule once they've checked the source page; this
// only flags what the extractor itself considered auto-eligible.
export function ConfidenceMeter({ confidence }: ConfidenceMeterProps) {
  const pct = Math.round(confidence * 100);
  const isLow = confidence < MIN_AUTO_ELIGIBLE_CONFIDENCE;

  return (
    <div className="flex items-center gap-2" aria-label={`${pct}% confidence`}>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div
          className={isLow ? 'h-full bg-amber-500' : 'h-full bg-emerald-500'}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground tabular-nums">{pct}%</span>
    </div>
  );
}
