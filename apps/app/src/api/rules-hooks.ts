'use client';

import { useQuery } from '@tanstack/react-query';

import { citationKey, getRule, getRuleCitation, listRules, ruleKeys } from './rules';
import type { RuleFilters } from './rules';

export function useRules(filters: RuleFilters = {}) {
  return useQuery({
    queryKey: ruleKeys.list(filters),
    queryFn: () => listRules(filters),
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
