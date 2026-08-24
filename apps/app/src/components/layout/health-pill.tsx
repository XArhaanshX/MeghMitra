'use client';

import { useHealth } from '@/api/health-hooks';
import { cn } from '@/lib/utils';

// GET /health never touches the database -- "unreachable" here means the API
// process itself is down, not that Postgres is. DB-backed routes 503 independently.
export function HealthPill() {
  const { data, isError, isPending } = useHealth();
  const isUp = !isPending && !isError && data?.status === 'ok';
  const label = isPending ? 'Checking API…' : isUp ? 'API online' : 'API unreachable';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
        isPending && 'border-border text-muted-foreground',
        isUp && 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
        !isPending && !isUp && 'border-destructive/40 bg-destructive/10 text-destructive'
      )}
    >
      <span
        className={cn(
          'size-1.5 rounded-full',
          isPending && 'bg-muted-foreground',
          isUp && 'bg-emerald-500',
          !isPending && !isUp && 'bg-destructive'
        )}
      />
      {label}
    </span>
  );
}
