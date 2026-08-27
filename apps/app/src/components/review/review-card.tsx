import Link from 'next/link';

import { ConfidenceMeter, ReviewStatusBadge } from '@/components/rules';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { hasValidCitation } from '@/schemas';
import type { DACPRule } from '@/schemas';

import { ApproveDialog } from './approve-dialog';
import { RejectDialog } from './reject-dialog';

interface ReviewCardProps {
  rule: DACPRule;
}

export function ReviewCard({ rule }: ReviewCardProps) {
  const { fields } = rule;
  // The one client-side approval guard the product allows: no citation, no
  // approve affordance. Never confidence (see approve-dialog.tsx).
  const canApprove = hasValidCitation(rule.citation);

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          {/* State before district: district names repeat across states, so a
              reviewer needs the state to know which plan they are approving. */}
          <p className="font-mono text-xs font-bold tracking-widest text-teal-deep uppercase">
            {fields.state} / {fields.district}
          </p>
          <CardTitle className="text-lg text-ink">{fields.condition}</CardTitle>
          <p className="text-sm text-ink-muted">
            {fields.crop ?? 'Crop not in source'}
            {fields.crop_stage ? `, ${fields.crop_stage}` : ''}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <ReviewStatusBadge status={rule.review_status} />
          <ConfidenceMeter confidence={rule.confidence} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <p className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">
            Proposed action
          </p>
          <p className="text-sm text-ink">{fields.action ?? 'No action recorded in the source.'}</p>
        </div>

        {rule.notes.length > 0 && (
          <div className="space-y-1">
            <p className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">
              Why it was flagged
            </p>
            <div className="space-y-1 text-sm text-ink">
              {rule.notes.map(note => (
                <p key={note}>{note}</p>
              ))}
            </div>
          </div>
        )}

        <div className="rounded-sm border border-sand-300 bg-sand-100/60 p-3">
          <p className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">
            Source
          </p>
          <p className="mt-1 font-mono text-sm font-bold text-ink">
            {rule.citation.document || 'No document on file'}
            {rule.citation.document && `, page ${rule.citation.page}`}
          </p>
          {rule.citation.source_text && (
            <p className="mt-1 font-mono text-sm text-ink-soft italic">
              &ldquo;{rule.citation.source_text}&rdquo;
            </p>
          )}
        </div>

        {!canApprove && (
          <p className="text-sm text-destructive-foreground">
            This rule cannot be approved: there is no valid citation to trace it back to.
          </p>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t-2 border-sand-300 pt-4">
          <ApproveDialog ruleId={rule.id} disabled={!canApprove} />
          <RejectDialog ruleId={rule.id} />
          <Link
            href={`/rules/${rule.id}`}
            className="font-mono text-sm text-teal-deep hover:underline"
          >
            Open full rule
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
