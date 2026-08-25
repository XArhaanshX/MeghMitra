import { dehydrate, HydrationBoundary } from '@tanstack/react-query';

import { listRules, ruleKeys } from '@/api/rules';
import { PageHeader } from '@/components/shared';
import { getQueryClient } from '@/lib/query';
import { reviewStatusSchema } from '@/schemas';

import { RulesFilters } from './_components/rules-filters';
import { RulesTable } from './_components/rules-table';

interface RulesPageProps {
  searchParams: Promise<{
    review_status?: string;
    state?: string;
    district?: string;
    advisory_eligible?: string;
  }>;
}

export default async function RulesPage({ searchParams }: RulesPageProps) {
  const params = await searchParams;
  // No default -- omitted state/district means every state, matching the
  // API's own contract. The dashboard's default view is India, not Haryana.
  const state = params.state;
  const district = params.district;
  const advisoryEligible = params.advisory_eligible === 'true' ? true : undefined;
  const reviewStatus = reviewStatusSchema.safeParse(params.review_status).data;

  const queryClient = getQueryClient();
  await queryClient.prefetchQuery({
    queryKey: ruleKeys.list({ reviewStatus, state, district, advisoryEligible }),
    queryFn: () => listRules({ reviewStatus, state, district, advisoryEligible }),
  });

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 px-6 py-12">
      <PageHeader
        title="Rules"
        description="Pre-approved DACP contingency actions retrieved from source documents, across every ingested state."
      />
      <RulesFilters />
      <HydrationBoundary state={dehydrate(queryClient)}>
        <RulesTable />
      </HydrationBoundary>
    </div>
  );
}
