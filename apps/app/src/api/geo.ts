import * as z from 'zod';

import { createQueryKeys } from '@/lib/query';
import { coverageResponseSchema, districtSummarySchema, stateSummarySchema } from '@/schemas';
import type { CoverageResponse, DistrictSummary, StateSummary } from '@/schemas';

import { request } from './request';

export const geoKeys = createQueryKeys('geo');
export const coverageKeys = createQueryKeys('coverage');

// Every state/district-scoped list query must carry this so a query key never
// omits `state` -- omitting it is what let a Bijapur-Karnataka fetch collide
// in the cache with a Bijapur-Chhattisgarh one before the backend required a
// district-name-collision-aware key. `district` is optional (state alone is
// a valid, coarser scope).
export interface GeoScope {
  state?: string;
  district?: string;
}

export function listStates(): Promise<StateSummary[]> {
  return request({ url: '/geo/states', schema: z.array(stateSummarySchema) });
}

export function listStateDistricts(stateCode: string): Promise<DistrictSummary[]> {
  return request({
    url: `/geo/states/${stateCode}/districts`,
    schema: z.array(districtSummarySchema),
  });
}

export function getCoverage(): Promise<CoverageResponse> {
  return request({ url: '/coverage', schema: coverageResponseSchema });
}
