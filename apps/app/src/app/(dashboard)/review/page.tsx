import { dehydrate, HydrationBoundary } from '@tanstack/react-query';

import { countReviewQueue, reviewKeys, reviewQueue } from '@/api/review';
import { PageHeader } from '@/components/shared';
import { getQueryClient } from '@/lib/query';

import { ReviewQueueList } from './_components/review-queue-list';

// Same static-prerender trap as the home page: the SSR prefetch here uses
// react-query's hydration boundary rather than plain `fetch()`, so Next never
// detects it as dynamic either. Client-side react-query would eventually
// self-heal (staleTime is 60s and the baked snapshot's `dataUpdatedAt` is
// from build time), but that still means every page load briefly shows a
// build-time-stale queue before the background refetch lands, which is wrong
// for a page whose entire purpose is showing live moderation state.
export const dynamic = 'force-dynamic';

const NUMBER_FORMAT = new Intl.NumberFormat('en-IN');

export default async function ReviewPage() {
  const queryClient = getQueryClient();

  // The queue list itself comes from the API's unpaginated path, which is
  // capped at 50 rows. Fetch the exact depth separately so the header states
  // the real backlog and the list can say when it is showing only a slice.
  const [total] = await Promise.all([
    countReviewQueue().catch(() => null),
    queryClient.prefetchQuery({ queryKey: reviewKeys.lists(), queryFn: reviewQueue }),
  ]);

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-6 py-10 sm:px-8 lg:py-14">
      <PageHeader
        title="Review queue"
        description="Extractions the pipeline would not approve on its own: ambiguous wording, low confidence, or a missing required field. Approving one puts it in the retrieval index."
        meta={
          total === null
            ? undefined
            : `${NUMBER_FORMAT.format(total)} ${total === 1 ? 'rule' : 'rules'} awaiting a decision`
        }
      />
      <HydrationBoundary state={dehydrate(queryClient)}>
        <ReviewQueueList total={total} />
      </HydrationBoundary>
    </div>
  );
}
