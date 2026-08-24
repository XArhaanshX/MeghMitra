'use client';

import { useRule, useRuleCitation } from '@/api/rules-hooks';
import { CitationPanel } from '@/components/citation';
import { ErrorState } from '@/components/shared';
import { Skeleton } from '@/components/ui/skeleton';

import { ReviewMeta } from './review-meta';
import { RuleFields } from './rule-fields';

interface RuleDetailProps {
  id: string;
}

export function RuleDetail({ id }: RuleDetailProps) {
  const { data: rule, isPending, isError, refetch } = useRule(id);
  // The dedicated GET /rules/{id}/citation endpoint -- the public "why" API,
  // fetched independently even though the rule payload already embeds it.
  const { data: citation, isPending: citationPending } = useRuleCitation(id);

  if (isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (isError) {
    return <ErrorState message="Failed to load rule." onRetry={() => void refetch()} />;
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          {rule.fields.crop ?? 'Crop not specified'}
        </h1>
        <p className="text-muted-foreground">{rule.fields.condition}</p>
      </div>
      <CitationPanel citation={citation} isLoading={citationPending} />
      <RuleFields fields={rule.fields} />
      <ReviewMeta rule={rule} />
    </div>
  );
}
