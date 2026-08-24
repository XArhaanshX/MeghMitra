'use client';

import Link from 'next/link';
import { useQueryStates } from 'nuqs';

import { useRules } from '@/api/rules-hooks';
import { ConditionCodeBadge, ConfidenceMeter, ReviewStatusBadge } from '@/components/rules';
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

import { rulesFilterParsers } from './rules-filters';
import { useDebouncedValue } from './use-debounced-value';

export function RulesTable() {
  const [filters] = useQueryStates(rulesFilterParsers);
  // District is free text -- debounce what feeds the fetch so typing doesn't
  // fire a request per keystroke. review_status/advisory_eligible are
  // discrete controls (select/checkbox) and don't need this.
  const district = useDebouncedValue(filters.district, 400);
  const {
    data: rules,
    isPending,
    isError,
    refetch,
  } = useRules({
    reviewStatus: filters.review_status ?? undefined,
    district: district || undefined,
    advisoryEligible: filters.advisory_eligible ?? undefined,
  });

  if (isPending) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return <ErrorState message="Failed to load rules." onRetry={() => void refetch()} />;
  }

  if (rules.length === 0) {
    return <EmptyState message="No rules. If this is a demo, run seed on the API." />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Crop</TableHead>
          <TableHead>Condition</TableHead>
          <TableHead>Action</TableHead>
          <TableHead>Condition code</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Confidence</TableHead>
          <TableHead>Citation</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rules.map(rule => (
          <TableRow key={rule.id}>
            <TableCell>
              <Link href={`/rules/${rule.id}`} className="font-medium hover:underline">
                {rule.fields.crop ?? 'Not specified'}
              </Link>
            </TableCell>
            <TableCell className="max-w-[220px]">
              <span className="block truncate" title={rule.fields.condition}>
                {rule.fields.condition}
              </span>
            </TableCell>
            <TableCell className="max-w-[200px]">
              <span className="block truncate" title={rule.fields.action ?? undefined}>
                {rule.fields.action ?? 'Not specified'}
              </span>
            </TableCell>
            <TableCell>
              <ConditionCodeBadge code={rule.fields.condition_code} />
            </TableCell>
            <TableCell>
              <ReviewStatusBadge status={rule.review_status} />
            </TableCell>
            <TableCell>
              <ConfidenceMeter confidence={rule.confidence} />
            </TableCell>
            <TableCell className="text-muted-foreground">
              {rule.citation.document} · p.{rule.citation.page}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
