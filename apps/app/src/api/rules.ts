import * as z from 'zod';

import { createQueryKeys } from '@/lib/query';
import { apiPageSchema, citationSchema, dacpRuleSchema } from '@/schemas';
import type { ApiPage, Citation, DACPRule, ReviewStatus } from '@/schemas';

import type { GeoScope } from './geo';
import { request } from './request';

export const ruleKeys = createQueryKeys('rules');

export function citationKey(id: string) {
  return [...ruleKeys.detail(id), 'citation'] as const;
}

export interface RuleFilters extends GeoScope {
  reviewStatus?: ReviewStatus;
  advisoryEligible?: boolean;
  limit?: number;
  offset?: number;
}

// `GET /rules` returns a bare array by default (backward-compatible with
// every existing caller) and switches to `{items, total, limit, offset}`
// only when `limit`/`offset` is sent -- see apps/api/app/deps.py::paginated.
// This client always unwraps to a plain array; callers that need `total`
// (e.g. a future pager control) should read the raw envelope via a
// dedicated call instead of overloading this one.
export function listRules(filters: RuleFilters = {}): Promise<DACPRule[]> {
  const params = {
    review_status: filters.reviewStatus,
    district: filters.district,
    state: filters.state,
    advisory_eligible: filters.advisoryEligible,
    limit: filters.limit,
    offset: filters.offset,
  };
  const bareOrPage = z.union([z.array(dacpRuleSchema), apiPageSchema(dacpRuleSchema)]);
  return request({ url: '/rules', params, schema: bareOrPage }).then(result =>
    Array.isArray(result) ? result : result.items
  );
}

// Paginated variant. Sending `limit` is what makes the API return the
// `{items, total, limit, offset}` envelope instead of a bare array, so this
// is the only way to learn how many rules match a filter. `listRules` above
// cannot: its bare-array path is capped at the server's `default_limit`
// (50), which silently truncates at India scale.
export function listRulesPage(
  filters: RuleFilters & { limit: number; offset: number }
): Promise<ApiPage<DACPRule>> {
  return request({
    url: '/rules',
    params: {
      review_status: filters.reviewStatus,
      district: filters.district,
      state: filters.state,
      advisory_eligible: filters.advisoryEligible,
      limit: filters.limit,
      offset: filters.offset,
    },
    schema: apiPageSchema(dacpRuleSchema),
  });
}

// Exact match count for a filter set, without transferring the rows. Asks
// for the smallest possible page and reads `total` off the envelope.
export function countRules(filters: RuleFilters = {}): Promise<number> {
  return listRulesPage({ ...filters, limit: 1, offset: 0 }).then(page => page.total);
}

export function getRule(id: string): Promise<DACPRule> {
  return request({ url: `/rules/${id}`, schema: dacpRuleSchema });
}

export function getRuleCitation(id: string): Promise<Citation> {
  return request({ url: `/rules/${id}/citation`, schema: citationSchema });
}
