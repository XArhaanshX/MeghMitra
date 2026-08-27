'use client';

import { useState } from 'react';
import Link from 'next/link';

import { useTriggerEventsPage } from '@/api/trigger-events-hooks';
import { EmptyState, ErrorState, Pagination } from '@/components/shared';
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

const PAGE_SIZE = 25;

interface TriggerEventsTabProps {
  highlightId?: string;
}

// Every evaluation, including the silent abstentions: the full audit trail,
// as opposed to the advisories tab, which lists emissions only.
export function TriggerEventsTab({ highlightId }: TriggerEventsTabProps) {
  const [offset, setOffset] = useState(0);
  const { data, isPending, isError, isFetching, refetch } = useTriggerEventsPage({
    limit: PAGE_SIZE,
    offset,
  });

  if (isPending) {
    return <Skeleton className="h-48 w-full" />;
  }
  if (isError) {
    return (
      <ErrorState message="Trigger events could not be loaded." onRetry={() => void refetch()} />
    );
  }
  if (data.items.length === 0) {
    return (
      <EmptyState
        message="No evaluation has run yet."
        hint="Every evaluation is recorded here, including the ones that produced no advisory. Run one from the Evaluate page."
      />
    );
  }

  const highlightOnPage =
    highlightId !== undefined && data.items.some(event => event.id === highlightId);

  return (
    <div className="space-y-4">
      {highlightId !== undefined && (
        <p className="rounded-sm border-2 border-teal bg-teal-soft px-4 py-3 text-sm text-teal-deep">
          {highlightOnPage
            ? 'The evaluation you came from is marked below.'
            : 'The evaluation you came from is not on this page. It may be further back in the log.'}
        </p>
      )}
      <div className="rounded-lg border-2 border-ink bg-sand-50">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Evaluated</TableHead>
              <TableHead>Block</TableHead>
              <TableHead>Condition</TableHead>
              <TableHead>Outcome</TableHead>
              <TableHead>Rule</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map(event => (
              <TableRow
                key={event.id}
                className={cn(event.id === highlightId && 'bg-teal-soft hover:bg-teal-soft')}
              >
                <TableCell className="whitespace-nowrap text-muted-foreground">
                  {new Date(event.detected_at).toLocaleString()}
                </TableCell>
                <TableCell className="font-mono text-xs">{event.block_key}</TableCell>
                <TableCell>
                  {event.condition ? event.condition.replaceAll('_', ' ') : 'None detected'}
                </TableCell>
                <TableCell className="max-w-[300px]">
                  {event.reasons.length > 0 ? (
                    <span className="block truncate" title={event.reasons.join('; ')}>
                      {event.reasons.join('; ')}
                    </span>
                  ) : (
                    <span className="text-ink-soft">Advisory issued</span>
                  )}
                </TableCell>
                <TableCell>
                  {event.rule_id ? (
                    <Link href={`/rules/${event.rule_id}`} className="text-primary hover:underline">
                      Open rule
                    </Link>
                  ) : (
                    <span className="text-ink-soft">None</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <Pagination
        total={data.total}
        limit={PAGE_SIZE}
        offset={data.offset}
        isFetching={isFetching}
        unit="evaluations"
        onOffsetChange={setOffset}
      />
    </div>
  );
}
