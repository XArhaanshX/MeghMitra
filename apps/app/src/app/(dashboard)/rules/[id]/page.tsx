import { notFound } from 'next/navigation';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';

import { isApiError } from '@/api';
import { citationKey, getRule, getRuleCitation, ruleKeys } from '@/api/rules';
import { getQueryClient } from '@/lib/query';

import { RuleDetail } from './_components/rule-detail';

interface RuleDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function RuleDetailPage({ params }: RuleDetailPageProps) {
  const { id } = await params;
  const queryClient = getQueryClient();

  try {
    await queryClient.fetchQuery({ queryKey: ruleKeys.detail(id), queryFn: () => getRule(id) });
  } catch (error) {
    if (isApiError(error) && error.status === 404) notFound();
    throw error;
  }

  await queryClient.prefetchQuery({
    queryKey: citationKey(id),
    queryFn: () => getRuleCitation(id),
  });

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 px-8 py-12 lg:px-12">
      <HydrationBoundary state={dehydrate(queryClient)}>
        <RuleDetail id={id} />
      </HydrationBoundary>
    </div>
  );
}
