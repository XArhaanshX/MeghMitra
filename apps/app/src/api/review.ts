import * as z from 'zod';

import { createQueryKeys } from '@/lib/query';
import { dacpRuleSchema } from '@/schemas';
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
