import { ApproveDialog, RejectDialog } from '@/components/review';
import { ConfidenceMeter, ReviewStatusBadge } from '@/components/rules';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { hasValidCitation } from '@/schemas';
import type { DACPRule } from '@/schemas';

interface ReviewMetaProps {
  rule: DACPRule;
}

const ACTIONABLE_STATUS: Record<DACPRule['review_status'], boolean> = {
  pending: true,
  needs_review: true,
  approved: false,
  rejected: false,
};

export function ReviewMeta({ rule }: ReviewMetaProps) {
  const canApprove = hasValidCitation(rule.citation);
  const canAct = ACTIONABLE_STATUS[rule.review_status];

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-4">
        <CardTitle className="text-lg">Review status</CardTitle>
        <div className="flex items-center gap-2">
          <ReviewStatusBadge status={rule.review_status} />
          <ConfidenceMeter confidence={rule.confidence} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {rule.notes.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Notes
            </p>
            <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
              {rule.notes.map(note => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        )}
        {rule.reviewed_by && (
          <p className="text-sm text-muted-foreground">
            Reviewed by {rule.reviewed_by}
            {rule.reviewed_at && ` on ${new Date(rule.reviewed_at).toLocaleString()}`}
          </p>
        )}
        {canAct && (
          <>
            {!canApprove && (
              <p className="text-sm text-destructive">
                No valid citation on file — this rule cannot be approved.
              </p>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <ApproveDialog ruleId={rule.id} disabled={!canApprove} />
              <RejectDialog ruleId={rule.id} />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
