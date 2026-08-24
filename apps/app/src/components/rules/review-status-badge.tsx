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
  pending: '',
  needs_review: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400',
  approved: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  rejected: 'line-through',
};

export function ReviewStatusBadge({ status }: ReviewStatusBadgeProps) {
  return (
    <Badge
      variant={status === 'pending' || status === 'rejected' ? 'secondary' : 'outline'}
      className={cn(STATUS_CLASS[status])}
    >
      {REVIEW_STATUS_LABEL[status]}
    </Badge>
  );
}
