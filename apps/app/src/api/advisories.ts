import * as z from 'zod';

import { createQueryKeys } from '@/lib/query';
import { advisorySchema, evaluateResponseSchema } from '@/schemas';
import type { Advisory, EvaluateRequest, EvaluateResponse } from '@/schemas';

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
