'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { approveRule, rejectRule, reviewKeys, reviewQueue } from './review';
import type { ApproveRuleInput, RejectRuleInput } from './review';
import { ruleKeys } from './rules';

export function useReviewQueue() {
  return useQuery({
    queryKey: reviewKeys.lists(),
    queryFn: reviewQueue,
  });
}

// Approving/rejecting moves a rule out of the queue and changes its
// review_status everywhere it's surfaced -- invalidate both caches rather
// than hand-patching individual query entries.
function useInvalidateRuleCaches() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: reviewKeys.all });
    void queryClient.invalidateQueries({ queryKey: ruleKeys.all });
  };
}

export function useApproveRule() {
  const invalidate = useInvalidateRuleCaches();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ApproveRuleInput }) => approveRule(id, body),
    onSuccess: invalidate,
  });
}

export function useRejectRule() {
  const invalidate = useInvalidateRuleCaches();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: RejectRuleInput }) => rejectRule(id, body),
    onSuccess: invalidate,
  });
}
