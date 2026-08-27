import * as z from 'zod';

import { createQueryKeys } from '@/lib/query';
import { apiPageSchema, dacpRuleSchema } from '@/schemas';
import type { DACPRule } from '@/schemas';

import { request } from './request';

export const reviewKeys = createQueryKeys('review-queue');

export interface ApproveRuleInput {
  reviewed_by: string;
}

export interface RejectRuleInput {
  reviewed_by: string;
  reason?: string;
}

export function reviewQueue(): Promise<DACPRule[]> {
  return request({ url: '/review-queue', schema: z.array(dacpRuleSchema) });
}

// Exact queue depth. `reviewQueue()` above returns the server's bare-array
// path, which is capped at `default_limit` (50), so counting its length
// undercounts a real backlog. Sending `limit` switches the API to the
// `{items, total, ...}` envelope; read `total` off that instead.
export function countReviewQueue(): Promise<number> {
  return request({
    url: '/review-queue',
    params: { limit: 1, offset: 0 },
    schema: apiPageSchema(dacpRuleSchema),
  }).then(page => page.total);
}

export function approveRule(id: string, body: ApproveRuleInput): Promise<DACPRule> {
  return request({
    url: `/rules/${id}/approve`,
    method: 'POST',
    data: body,
    schema: dacpRuleSchema,
  });
}

export function rejectRule(id: string, body: RejectRuleInput): Promise<DACPRule> {
  return request({
    url: `/rules/${id}/reject`,
    method: 'POST',
    data: body,
    schema: dacpRuleSchema,
  });
}
