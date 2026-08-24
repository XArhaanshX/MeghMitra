import * as z from 'zod';

import { createQueryKeys } from '@/lib/query';
import { triggerEventSchema } from '@/schemas';
import type { TriggerEvent } from '@/schemas';

import { request } from './request';

export const triggerEventKeys = createQueryKeys('trigger-events');

// Every evaluation, including silent ABSTAINs -- the full audit trail
// (as opposed to GET /advisories, which is non-silent emissions only).
export function listTriggerEvents(): Promise<TriggerEvent[]> {
  return request({ url: '/trigger-events', schema: z.array(triggerEventSchema) });
}
