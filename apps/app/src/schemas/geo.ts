import * as z from 'zod';

// Mirrors apps/api/app/routes/geo.py's StateSummary/DistrictSummary/CoverageResponse.
export const regionKindSchema = z.enum(['state', 'union_territory']);
export type RegionKind = z.infer<typeof regionKindSchema>;

export const stateSummarySchema = z.object({
  state_code: z.string(),
  name: z.string(),
  slug: z.string(),
  kind: regionKindSchema,
  has_dacp_coverage: z.boolean(),
  document_count: z.number().int().min(0),
  district_count: z.number().int().min(0),
});
export type StateSummary = z.infer<typeof stateSummarySchema>;

export const districtSummarySchema = z.object({
  district_code: z.string(),
  name: z.string(),
  slug: z.string(),
});
export type DistrictSummary = z.infer<typeof districtSummarySchema>;

export const coverageResponseSchema = z.object({
  documents: z.number().int().min(0),
  rules: z.number().int().min(0),
  approved_rules: z.number().int().min(0),
  unmapped_rules: z.number().int().min(0),
  districts: z.number().int().min(0),
  district_name_collisions: z.number().int().min(0),
  by_code: z.record(z.string(), z.number().int()),
  by_review_status: z.record(z.string(), z.number().int()),
});
export type CoverageResponse = z.infer<typeof coverageResponseSchema>;

// Additive pagination envelope -- matches apps/api/app/deps.py's `paginated()`
// exactly (`{items, total, limit, offset}`), distinct from the generic
// page/pageSize shape in `common.ts` which no backend endpoint actually uses.
export function apiPageSchema<T extends z.ZodType>(itemSchema: T) {
  return z.object({
    items: z.array(itemSchema),
    total: z.number().int().min(0),
    limit: z.number().int().min(1),
    offset: z.number().int().min(0),
  });
}
export type ApiPage<T> = { items: T[]; total: number; limit: number; offset: number };
