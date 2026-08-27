import * as z from 'zod';

import { createQueryKeys } from '@/lib/query';
import { apiPageSchema, triggerEventSchema } from '@/schemas';
import type { ApiPage, TriggerEvent } from '@/schemas';

import { request } from './request';

export const triggerEventKeys = createQueryKeys('trigger-events');

// Every evaluation, including silent ABSTAINs -- the full audit trail
// (as opposed to GET /advisories, which is non-silent emissions only).
export function listTriggerEvents(): Promise<TriggerEvent[]> {
  return request({ url: '/trigger-events', schema: z.array(triggerEventSchema) });
}

// Paged read over the full audit trail. See listAdvisoriesPage for why the
// bare-array path is unsuitable for a log that only grows.
export function listTriggerEventsPage(
  page: { limit: number; offset: number }
): Promise<ApiPage<TriggerEvent>> {
  return request({
    url: '/trigger-events',
    params: { limit: page.limit, offset: page.offset },
    schema: apiPageSchema(triggerEventSchema),
  });
}
