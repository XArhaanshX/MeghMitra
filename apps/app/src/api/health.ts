import * as z from 'zod';

import { request } from './request';

const healthSchema = z.object({ status: z.string() });
export type Health = z.infer<typeof healthSchema>;

export const healthKey = ['health'] as const;

// Never touches the database -- reports process liveness only. DB-backed
// routes 503 independently; this endpoint always 200s once the process is up.
export function getHealth(): Promise<Health> {
  return request({ url: '/health', schema: healthSchema });
}
