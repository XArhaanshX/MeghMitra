'use client';

import { useHealth } from '@/api/health-hooks';
import { cn } from '@/lib/utils';

// GET /health never touches the database -- "unreachable" here means the API
// process itself is down, not that Postgres is. DB-backed routes 503 independently.
export function HealthPill() {
  const { data, isError, isPending } = useHealth();
  const isUp = !isPending && !isError && data?.status === 'ok';
  const label = isPending ? 'Checking API' : isUp ? 'API online' : 'API unreachable';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full border-2 border-ink px-3 py-1 font-mono text-xs font-bold tracking-wide uppercase',
        isPending && 'bg-sand-100 text-ink-soft',
        isUp && 'bg-moss-soft text-moss',
        !isPending && !isUp && 'bg-destructive text-destructive-foreground'
      )}
    >
      <span
        className={cn(
          'size-2 shrink-0 rounded-full',
          isPending && 'bg-ink-soft',
          isUp && 'bg-moss',
          !isPending && !isUp && 'bg-destructive-foreground'
        )}
      />
      {label}
    </span>
  );
}
