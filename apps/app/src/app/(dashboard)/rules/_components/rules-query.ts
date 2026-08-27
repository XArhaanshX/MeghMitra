import {
  createLoader,
  parseAsBoolean,
  parseAsIndex,
  parseAsString,
  parseAsStringEnum,
} from 'nuqs/server';

import { listRulesPage, ruleKeys } from '@/api/rules';
import type { RuleFilters } from '@/api/rules';
import { reviewStatusSchema } from '@/schemas';

// One page of an eight-column table: dense enough to be worth scanning,
// short enough that the pager stays reachable without a long scroll.
export const RULES_PAGE_SIZE = 25;

// Single source of truth for the rules URL contract, shared by the server
// page (via `loadRulesFilters`) and the client filter bar and table (via
// `useQueryStates`). Defining it once is what keeps the SSR prefetch and the
// client query on the same cache key instead of drifting into a double fetch.
//
// No default for state or district: omitted means every state, matching the
// API's own contract. A hardcoded default here previously snapped every
// fresh load and every cleared filter back to Sirsa/Haryana, which is
// exactly the Haryana-first behaviour this filter must not have.
export const rulesFilterParsers = {
  review_status: parseAsStringEnum(reviewStatusSchema.options),
  state: parseAsString,
  district: parseAsString,
  advisory_eligible: parseAsBoolean,
  // 1-based in the URL, 0-based in code, which is what `parseAsIndex` is for.
  page: parseAsIndex.withDefault(0),
};

export const loadRulesFilters = createLoader(rulesFilterParsers);

export type RulesFilterValues = {
  review_status: (typeof reviewStatusSchema.options)[number] | null;
  state: string | null;
  district: string | null;
  advisory_eligible: boolean | null;
  page: number;
};

export function toRuleFilters(
  values: RulesFilterValues
): RuleFilters & { limit: number; offset: number } {
  return {
    reviewStatus: values.review_status ?? undefined,
    state: values.state ?? undefined,
    district: values.district ?? undefined,
    advisoryEligible: values.advisory_eligible ?? undefined,
    limit: RULES_PAGE_SIZE,
    offset: values.page * RULES_PAGE_SIZE,
  };
}

// Must stay in lockstep with `useRulesPage`'s key so the server prefetch
// actually hydrates the client query.
export function rulesPageQuery(values: RulesFilterValues) {
  const filters = toRuleFilters(values);
  return {
    queryKey: [...ruleKeys.list(filters), 'page'] as const,
    queryFn: () => listRulesPage(filters),
  };
}
