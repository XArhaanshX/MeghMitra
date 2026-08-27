import * as z from 'zod';

import { createQueryKeys } from '@/lib/query';
import { advisorySchema, apiPageSchema, evaluateResponseSchema } from '@/schemas';
import type { Advisory, ApiPage, EvaluateRequest, EvaluateResponse } from '@/schemas';

import { request } from './request';

export const advisoryKeys = createQueryKeys('advisories');

// The retrieve-or-abstain decision. 201 on success; `abstain` is a normal
// response, not an error -- never treat it as a failed request.
export function evaluate(body: EvaluateRequest): Promise<EvaluateResponse> {
  return request({
    url: '/advisories',
    method: 'POST',
    data: body,
    schema: evaluateResponseSchema,
  });
}

export function listAdvisories(): Promise<Advisory[]> {
  return request({ url: '/advisories', schema: z.array(advisorySchema) });
}

// The audit log grows with every evaluation and is never pruned, so the
// browsing view reads it a page at a time. Sending `limit` switches the API
// to the `{items, total, ...}` envelope; without it the response is a bare
// array silently capped at 50.
export function listAdvisoriesPage(
  page: { limit: number; offset: number }
): Promise<ApiPage<Advisory>> {
  return request({
    url: '/advisories',
    params: { limit: page.limit, offset: page.offset },
    schema: apiPageSchema(advisorySchema),
  });
}
