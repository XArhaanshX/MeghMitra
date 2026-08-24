'use client';

import Link from 'next/link';

import { useAdvisories } from '@/api/advisories-hooks';
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

// Advisories = things Ankur SAID -- non-silent emissions only.
export function AdvisoriesTab() {
  const { data: advisories, isPending, isError, refetch } = useAdvisories();

  if (isPending) {
    return <Skeleton className="h-48 w-full" />;
  }
  if (isError) {
    return <ErrorState message="Failed to load advisories." onRetry={() => void refetch()} />;
  }
  if (advisories.length === 0) {
    return <EmptyState message="No advisories emitted yet." />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>Action</TableHead>
          <TableHead>Reason</TableHead>
          <TableHead>Channel</TableHead>
          <TableHead>Rule</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {advisories.map(advisory => (
          <TableRow key={advisory.id}>
            <TableCell className="text-muted-foreground">
              {new Date(advisory.generated_at).toLocaleString()}
            </TableCell>
            <TableCell className="font-medium uppercase">{advisory.action}</TableCell>
            <TableCell className="max-w-[280px] truncate" title={advisory.reason ?? undefined}>
              {advisory.reason ?? '—'}
            </TableCell>
            <TableCell>{advisory.channel}</TableCell>
            <TableCell>
              {advisory.rule_id ? (
                <Link href={`/rules/${advisory.rule_id}`} className="text-primary hover:underline">
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
