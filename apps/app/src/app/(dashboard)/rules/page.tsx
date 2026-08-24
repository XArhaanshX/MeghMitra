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
    district?: string;
    advisory_eligible?: string;
  }>;
}

export default async function RulesPage({ searchParams }: RulesPageProps) {
  const params = await searchParams;
  const district = params.district ?? 'Sirsa';
  const advisoryEligible = params.advisory_eligible === 'true' ? true : undefined;
  const reviewStatus = reviewStatusSchema.safeParse(params.review_status).data;

  const queryClient = getQueryClient();
  await queryClient.prefetchQuery({
    queryKey: ruleKeys.list({ reviewStatus, district, advisoryEligible }),
    queryFn: () => listRules({ reviewStatus, district, advisoryEligible }),
  });

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 px-6 py-12">
      <PageHeader
        title="Rules"
        description="Pre-approved DACP contingency actions retrieved from source documents."
      />
      <RulesFilters />
      <HydrationBoundary state={dehydrate(queryClient)}>
        <RulesTable />
      </HydrationBoundary>
    </div>
  );
}
