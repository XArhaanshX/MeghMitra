'use client';

import { useState } from 'react';
import Link from 'next/link';

import { useAdvisoriesPage } from '@/api/advisories-hooks';
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

const PAGE_SIZE = 25;

// Advisories are what the system SAID: non-silent emissions only. The
// trigger-events tab beside this one holds every evaluation including the
// silent ones.
export function AdvisoriesTab() {
  const [offset, setOffset] = useState(0);
  const { data, isPending, isError, isFetching, refetch } = useAdvisoriesPage({
    limit: PAGE_SIZE,
    offset,
  });

  if (isPending) {
    return <Skeleton className="h-48 w-full" />;
  }
  if (isError) {
    return <ErrorState message="Advisories could not be loaded." onRetry={() => void refetch()} />;
  }
  if (data.items.length === 0) {
    return (
      <EmptyState
        message="No advisory has been issued yet."
        hint="An advisory appears here only when an evaluation matches an approved, cited rule. Run one from the Evaluate page."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border-2 border-ink bg-sand-50">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Issued</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Channel</TableHead>
              <TableHead>Rule</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map(advisory => (
              <TableRow key={advisory.id}>
                <TableCell className="whitespace-nowrap text-muted-foreground">
                  {new Date(advisory.generated_at).toLocaleString()}
                </TableCell>
                <TableCell className="font-medium uppercase">
                  {advisory.action.replaceAll('_', ' ')}
                </TableCell>
                <TableCell className="max-w-[280px]">
                  <span className="block truncate" title={advisory.reason ?? undefined}>
                    {advisory.reason ?? 'Not recorded'}
                  </span>
                </TableCell>
                <TableCell>{advisory.channel}</TableCell>
                <TableCell>
                  {advisory.rule_id ? (
                    <Link
                      href={`/rules/${advisory.rule_id}`}
                      className="text-primary hover:underline"
                    >
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
        unit="advisories"
        onOffsetChange={setOffset}
      />
    </div>
  );
}
