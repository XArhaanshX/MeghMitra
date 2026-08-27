import type { SearchParams } from 'nuqs/server';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';

import { PageHeader } from '@/components/shared';
import { getQueryClient } from '@/lib/query';

import { RulesFilters } from './_components/rules-filters';
import { loadRulesFilters, rulesPageQuery } from './_components/rules-query';
import { RulesTable } from './_components/rules-table';

interface RulesPageProps {
  searchParams: Promise<SearchParams>;
}

export default async function RulesPage({ searchParams }: RulesPageProps) {
  // Parsed with the same parser map the client filter bar uses, so the
  // prefetched cache entry lands on exactly the key the table asks for.
  const filters = await loadRulesFilters(searchParams);

  const queryClient = getQueryClient();
  await queryClient.prefetchQuery(rulesPageQuery(filters));

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 px-6 py-10 sm:px-8 lg:py-14">
      <PageHeader
        title="Rules"
        description="Contingency actions extracted verbatim from District Agriculture Contingency Plans. Every state with an ingested plan is included; filter to narrow the list."
      />
      <RulesFilters />
      <HydrationBoundary state={dehydrate(queryClient)}>
        <RulesTable />
      </HydrationBoundary>
    </div>
  );
}
