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
  // approve affordance -- never confidence (see approve-dialog.tsx).
  const canApprove = hasValidCitation(rule.citation);

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <CardTitle className="text-xl">{fields.crop ?? 'Crop not specified'}</CardTitle>
          <p className="text-sm text-muted-foreground">{fields.condition}</p>
          <p className="text-sm">{fields.action ?? 'No action recorded'}</p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <ReviewStatusBadge status={rule.review_status} />
          <ConfidenceMeter confidence={rule.confidence} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {rule.notes.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Why it was flagged
            </p>
            <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
              {rule.notes.map(note => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="rounded-md border bg-muted/40 p-3 text-sm">
          <p className="font-medium">
            {rule.citation.document} · page {rule.citation.page}
          </p>
          {rule.citation.source_text && (
            <p className="mt-1 text-muted-foreground italic">
              &ldquo;{rule.citation.source_text}&rdquo;
            </p>
          )}
        </div>
        {!canApprove && (
          <p className="text-sm text-destructive">
            No valid citation on file — this rule cannot be approved.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <ApproveDialog ruleId={rule.id} disabled={!canApprove} />
          <RejectDialog ruleId={rule.id} />
          <Link href={`/rules/${rule.id}`} className="text-sm text-primary hover:underline">
            View full rule
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
