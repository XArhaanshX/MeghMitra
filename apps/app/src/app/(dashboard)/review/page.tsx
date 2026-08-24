import { dehydrate, HydrationBoundary } from '@tanstack/react-query';

import { reviewKeys, reviewQueue } from '@/api/review';
import { PageHeader } from '@/components/shared';
import { getQueryClient } from '@/lib/query';

import { ReviewQueueList } from './_components/review-queue-list';

export default async function ReviewPage() {
  const queryClient = getQueryClient();
  await queryClient.prefetchQuery({ queryKey: reviewKeys.lists(), queryFn: reviewQueue });

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-6 py-12">
      <PageHeader
        title="Review queue"
        description="Rules flagged for human review — ambiguous, low-confidence, or missing required fields."
      />
      <HydrationBoundary state={dehydrate(queryClient)}>
        <ReviewQueueList />
      </HydrationBoundary>
    </div>
  );
}
