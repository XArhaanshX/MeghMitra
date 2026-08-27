'use client';

import { useQuery } from '@tanstack/react-query';

import {
  citationKey,
  getRule,
  getRuleCitation,
  listRules,
  listRulesPage,
  ruleKeys,
} from './rules';
import type { RuleFilters } from './rules';

export function useRules(filters: RuleFilters = {}) {
  return useQuery({
    queryKey: ruleKeys.list(filters),
    queryFn: () => listRules(filters),
  });
}

// Paged read: keeps the previous page on screen while the next one loads so
// paging doesn't blank the table, and exposes `total` for the range readout.
export function useRulesPage(filters: RuleFilters & { limit: number; offset: number }) {
  return useQuery({
    queryKey: [...ruleKeys.list(filters), 'page'] as const,
    queryFn: () => listRulesPage(filters),
    placeholderData: previous => previous,
  });
}

export function useRule(id: string) {
  return useQuery({
    queryKey: ruleKeys.detail(id),
    queryFn: () => getRule(id),
  });
}

export function useRuleCitation(id: string) {
  return useQuery({
    queryKey: citationKey(id),
    queryFn: () => getRuleCitation(id),
  });
}
