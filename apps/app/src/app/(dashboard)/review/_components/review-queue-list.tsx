'use client';

import { useReviewQueue } from '@/api/review-hooks';
import { ReviewCard } from '@/components/review';
import { EmptyState, ErrorState } from '@/components/shared';
import { Skeleton } from '@/components/ui/skeleton';

export function ReviewQueueList() {
  const { data: rules, isPending, isError, refetch } = useReviewQueue();

  if (isPending) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-40 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return <ErrorState message="Failed to load the review queue." onRetry={() => void refetch()} />;
  }

  if (rules.length === 0) {
    return <EmptyState message="Queue clear." />;
  }

  return (
    <ul className="space-y-4">
      {rules.map(rule => (
        <li key={rule.id}>
          <ReviewCard rule={rule} />
        </li>
      ))}
    </ul>
  );
}
