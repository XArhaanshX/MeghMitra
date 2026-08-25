import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ReviewStatus } from '@/schemas';

interface ReviewStatusBadgeProps {
  status: ReviewStatus;
}

export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  pending: 'Pending',
  needs_review: 'Needs review',
  approved: 'Approved',
  rejected: 'Rejected',
};

// Never colour-only -- the label always renders alongside the colour.
const STATUS_CLASS: Record<ReviewStatus, string> = {
  pending: 'bg-sand-100 text-ink-muted',
  needs_review: 'bg-teal-soft text-teal-deep',
  approved: 'bg-moss-soft text-moss',
  rejected: 'bg-destructive text-destructive-foreground line-through',
};

export function ReviewStatusBadge({ status }: ReviewStatusBadgeProps) {
  return (
    <Badge variant="outline" className={cn('border-ink', STATUS_CLASS[status])}>
      {REVIEW_STATUS_LABEL[status]}
    </Badge>
  );
}
