import { dehydrate, HydrationBoundary } from '@tanstack/react-query';

import { reviewKeys, reviewQueue } from '@/api/review';
import { PageHeader } from '@/components/shared';
import { getQueryClient } from '@/lib/query';

import { ReviewQueueList } from './_components/review-queue-list';

// Same static-prerender trap as the home page -- the SSR prefetch here uses
// react-query's hydration boundary rather than plain `fetch()`, so Next
// never detects it as dynamic either. Client-side react-query would
// eventually self-heal (staleTime is 60s and the baked snapshot's
// `dataUpdatedAt` is from build time), but that still means every page load
// briefly shows a build-time-stale queue before the background refetch
// lands -- wrong for a page whose entire purpose is showing live moderation
// state. Force per-request rendering instead.
export const dynamic = 'force-dynamic';

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
