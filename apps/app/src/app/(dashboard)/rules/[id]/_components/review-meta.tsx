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
    <Card className="bg-teal-soft">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-4">
        <CardTitle className="text-lg text-ink">Review</CardTitle>
        <ReviewStatusBadge status={rule.review_status} />
      </CardHeader>
      <CardContent className="space-y-4">
        <ConfidenceMeter confidence={rule.confidence} variant="full" />
        <p className="text-sm text-ink-muted">
          Confidence describes how cleanly the extractor read this row. It never decides approval:
          only a reviewer does, and only when a citation is present.
        </p>

        {rule.notes.length > 0 && (
          <div className="space-y-1">
            <p className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">
              Notes
            </p>
            <div className="space-y-2 text-sm text-ink">
              {rule.notes.map(note => (
                <p key={note}>{note}</p>
              ))}
            </div>
          </div>
        )}

        <p className="font-mono text-xs text-ink-soft">
          {rule.reviewed_by
            ? `Reviewed by ${rule.reviewed_by}${rule.reviewed_at ? ` on ${new Date(rule.reviewed_at).toLocaleString()}` : ''}`
            : 'Flagged by the extractor. No human decision recorded yet.'}
        </p>

        {canAct && (
          <div className="space-y-3 border-t-2 border-teal-deep/30 pt-4">
            <div className="flex flex-wrap items-center gap-3">
              <ApproveDialog ruleId={rule.id} disabled={!canApprove} />
              <RejectDialog ruleId={rule.id} />
            </div>
            {!canApprove && (
              <p className="rounded-sm border border-teal-deep/40 bg-sand-50 p-3 text-sm text-ink-muted">
                Approval is blocked because this rule has no valid source citation. A citation
                naming the document and page is required before it can enter the retrieval index.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
