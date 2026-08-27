'use client';

import Link from 'next/link';
import { useQueryStates } from 'nuqs';

import { useRulesPage } from '@/api/rules-hooks';
import { ConditionCodeBadge, ConfidenceMeter, ReviewStatusBadge } from '@/components/rules';
import { EmptyState, ErrorState, Pagination } from '@/components/shared';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import { RULES_PAGE_SIZE, rulesFilterParsers, toRuleFilters } from './rules-query';

export function RulesTable() {
  const [filters, setFilters] = useQueryStates(rulesFilterParsers);
  // State and district are discrete Selects, so a selection fires exactly one
  // fetch and no debounce is needed.
  const { data, isPending, isError, isFetching, refetch } = useRulesPage(toRuleFilters(filters));

  if (isPending) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return <ErrorState message="Rules could not be loaded." onRetry={() => void refetch()} />;
  }

  if (data.items.length === 0) {
    // `?page=N` is a shareable URL, so it can point past the end of a result
    // set that has since shrunk (or been filtered down). That is a different
    // situation from "nothing matches" and needs a different way out.
    if (data.total > 0 && filters.page > 0) {
      return (
        <EmptyState
          message="This page is empty."
          hint={`These filters match ${data.total} ${data.total === 1 ? 'rule' : 'rules'}, which fit on earlier pages.`}
          action={
            <Button variant="outline" size="sm" onClick={() => void setFilters({ page: null })}>
              Back to the first page
            </Button>
          }
        />
      );
    }

    const scope = [filters.district, filters.state].filter(Boolean).join(', ');
    return (
      <EmptyState
        message={scope ? `No rules for ${scope}.` : 'No rules match these filters.'}
        hint={
          scope
            ? 'That district may have no ingested contingency plan yet, or no rule in it matches the other filters. Coverage is reported honestly rather than filled in.'
            : 'Try clearing a filter. If the corpus is empty, run the seed task against the API.'
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border-2 border-ink bg-sand-50">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Region</TableHead>
              <TableHead>Crop</TableHead>
              <TableHead>Condition</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Classified as</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Source</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map(rule => (
              <TableRow key={rule.id}>
                <TableCell className="whitespace-nowrap">
                  <span className="block font-medium text-ink">{rule.fields.state}</span>
                  <span className="block text-xs text-ink-soft">{rule.fields.district}</span>
                </TableCell>
                <TableCell>
                  <Link href={`/rules/${rule.id}`} className="font-medium hover:underline">
                    {rule.fields.crop ?? 'Not in source'}
                  </Link>
                </TableCell>
                <TableCell className="max-w-[220px]">
                  <span className="block truncate" title={rule.fields.condition}>
                    {rule.fields.condition}
                  </span>
                </TableCell>
                <TableCell className="max-w-[200px]">
                  <span className="block truncate" title={rule.fields.action ?? undefined}>
                    {rule.fields.action ?? 'Not in source'}
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
                <TableCell className="max-w-[180px] text-muted-foreground">
                  <span className="block truncate" title={rule.citation.document}>
                    {rule.citation.document}
                  </span>
                  <span className="block text-xs">page {rule.citation.page}</span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <Pagination
        total={data.total}
        limit={RULES_PAGE_SIZE}
        offset={data.offset}
        isFetching={isFetching}
        unit="rules"
        onOffsetChange={offset =>
          void setFilters({ page: Math.floor(offset / RULES_PAGE_SIZE) || null })
        }
      />
    </div>
  );
}
