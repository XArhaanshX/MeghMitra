'use client';

import Link from 'next/link';

import { useTriggerEvents } from '@/api/trigger-events-hooks';
import { EmptyState, ErrorState } from '@/components/shared';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';

interface TriggerEventsTabProps {
  highlightId?: string;
}

// Trigger events = every evaluation, including silent ABSTAINs -- the full
// audit trail (as opposed to the Advisories tab, which is non-silent only).
export function TriggerEventsTab({ highlightId }: TriggerEventsTabProps) {
  const { data: events, isPending, isError, refetch } = useTriggerEvents();

  if (isPending) {
    return <Skeleton className="h-48 w-full" />;
  }
  if (isError) {
    return <ErrorState message="Failed to load trigger events." onRetry={() => void refetch()} />;
  }
  if (events.length === 0) {
    return <EmptyState message="No trigger events recorded yet." />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>Block</TableHead>
          <TableHead>Condition</TableHead>
          <TableHead>Reasons</TableHead>
          <TableHead>Rule</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map(event => (
          <TableRow
            key={event.id}
            className={cn(event.id === highlightId && 'bg-primary/10 hover:bg-primary/15')}
          >
            <TableCell className="text-muted-foreground">
              {new Date(event.detected_at).toLocaleString()}
            </TableCell>
            <TableCell>{event.block_key}</TableCell>
            <TableCell>{event.condition ?? 'None detected'}</TableCell>
            <TableCell className="max-w-[280px] truncate" title={event.reasons.join('; ')}>
              {event.reasons.length > 0 ? event.reasons.join('; ') : '—'}
            </TableCell>
            <TableCell>
              {event.rule_id ? (
                <Link href={`/rules/${event.rule_id}`} className="text-primary hover:underline">
                  View rule
                </Link>
              ) : (
                '—'
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
