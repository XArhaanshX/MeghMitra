'use client';

import { Button } from '@/components/ui/button';

interface PaginationProps {
  /** Total rows matching the current filters, from the API envelope. */
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
  /** True while the next page is in flight; the previous page stays visible. */
  isFetching?: boolean;
  /** Plural noun for the range readout, e.g. "rules". */
  unit?: string;
}

// Indian digit grouping, stated explicitly rather than left to the runtime
// locale, so the server and client render the same string.
const NUMBER_FORMAT = new Intl.NumberFormat('en-IN');

export function Pagination({
  total,
  limit,
  offset,
  onOffsetChange,
  isFetching = false,
  unit = 'results',
}: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const currentPage = Math.floor(offset / limit) + 1;
  const first = total === 0 ? 0 : offset + 1;
  const last = Math.min(offset + limit, total);
  const hasPrevious = offset > 0;
  const hasNext = last < total;

  // One page of results needs no controls, but the count is still worth
  // stating so the reader knows the table is complete.
  if (total <= limit) {
    return (
      <p className="font-mono text-xs text-ink-soft">
        {NUMBER_FORMAT.format(total)} {unit}, all shown
      </p>
    );
  }

  return (
    <nav
      aria-label={`${unit} pagination`}
      className="flex flex-wrap items-center justify-between gap-4 border-t-2 border-ink pt-4"
    >
      {/* aria-live so paging announces the new range to a screen reader
          instead of silently replacing rows. */}
      <p aria-live="polite" className="font-mono text-xs text-ink-soft">
        <span className="font-bold text-ink">
          {NUMBER_FORMAT.format(first)} to {NUMBER_FORMAT.format(last)}
        </span>{' '}
        of {NUMBER_FORMAT.format(total)} {unit}
        {isFetching && <span className="ml-2 text-ink-soft">loading</span>}
      </p>
      <div className="flex items-center gap-3">
        <span className="font-mono text-xs text-ink-soft tabular-nums">
          Page {NUMBER_FORMAT.format(currentPage)} of {NUMBER_FORMAT.format(pageCount)}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={!hasPrevious}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!hasNext}
          onClick={() => onOffsetChange(offset + limit)}
        >
          Next
        </Button>
      </div>
    </nav>
  );
}
