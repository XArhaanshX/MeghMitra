'use client';

import { useReviewQueue } from '@/api/review-hooks';
import { ReviewCard } from '@/components/review';
import { EmptyState, ErrorState } from '@/components/shared';
import { Skeleton } from '@/components/ui/skeleton';

interface ReviewQueueListProps {
  /** Exact queue depth from the server, or null if that count failed. */
  total: number | null;
}

export function ReviewQueueList({ total }: ReviewQueueListProps) {
  const { data: rules, isPending, isError, refetch } = useReviewQueue();

  if (isPending) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-56 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState message="The review queue could not be loaded." onRetry={() => void refetch()} />
    );
  }

  if (rules.length === 0) {
    return (
      <EmptyState
        message="Nothing awaiting review."
        hint="Every extracted rule has been approved or rejected. New items appear here when a plan is ingested and the extractor is unsure."
      />
    );
  }

  const withheld = total === null ? 0 : total - rules.length;

  return (
    <div className="space-y-4">
      <ul className="space-y-4">
        {rules.map(rule => (
          <li key={rule.id}>
            <ReviewCard rule={rule} />
          </li>
        ))}
      </ul>
      {withheld > 0 && (
        <p className="rounded-sm border-2 border-dashed border-sand-300 bg-sand-50/60 px-4 py-3 font-mono text-xs text-ink-soft">
          Showing the {rules.length} oldest items. {withheld} more are queued and appear as these
          are cleared.
        </p>
      )}
    </div>
  );
}
