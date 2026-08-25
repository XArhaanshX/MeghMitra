'use client';

import Link from 'next/link';

import { useRule, useRuleCitation } from '@/api/rules-hooks';
import { CitationPanel } from '@/components/citation';
import { ReviewStatusBadge } from '@/components/rules';
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
    <div className="space-y-8">
      <Link
        href="/rules"
        className="inline-flex items-center gap-1 font-mono text-xs font-bold tracking-widest text-ink-soft uppercase hover:text-ink"
      >
        ← Rules
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="font-mono text-xs font-bold tracking-widest text-teal-deep uppercase">
            {rule.fields.crop ?? 'Crop not specified'}
          </p>
          <h1 className="max-w-3xl font-heading text-3xl leading-tight font-bold tracking-tight text-ink sm:text-4xl">
            {rule.fields.condition}
          </h1>
        </div>
        <ReviewStatusBadge status={rule.review_status} />
      </div>
      <CitationPanel citation={citation} isLoading={citationPending} />
      <RuleFields fields={rule.fields} />
      <ReviewMeta rule={rule} />
    </div>
  );
}
