import * as z from 'zod';

import { createQueryKeys } from '@/lib/query';
import { citationSchema, dacpRuleSchema } from '@/schemas';
import type { Citation, DACPRule, ReviewStatus } from '@/schemas';

import { request } from './request';

export const ruleKeys = createQueryKeys('rules');

export function citationKey(id: string) {
  return [...ruleKeys.detail(id), 'citation'] as const;
}

export interface RuleFilters {
  reviewStatus?: ReviewStatus;
  district?: string;
  advisoryEligible?: boolean;
}

export function listRules(filters: RuleFilters = {}): Promise<DACPRule[]> {
  return request({
    url: '/rules',
    params: {
      review_status: filters.reviewStatus,
      district: filters.district,
      advisory_eligible: filters.advisoryEligible,
    },
    schema: z.array(dacpRuleSchema),
  });
}

export function getRule(id: string): Promise<DACPRule> {
  return request({ url: `/rules/${id}`, schema: dacpRuleSchema });
}

export function getRuleCitation(id: string): Promise<Citation> {
  return request({ url: `/rules/${id}/citation`, schema: citationSchema });
}
