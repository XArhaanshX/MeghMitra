'use client';

import { useMutation, useQuery } from '@tanstack/react-query';

import type { EvaluateRequest } from '@/schemas';

import { advisoryKeys, evaluate, listAdvisories, listAdvisoriesPage } from './advisories';

export function useAdvisories() {
  return useQuery({
    queryKey: advisoryKeys.lists(),
    queryFn: listAdvisories,
  });
}

export function useAdvisoriesPage(page: { limit: number; offset: number }) {
  return useQuery({
    queryKey: advisoryKeys.list(page),
    queryFn: () => listAdvisoriesPage(page),
    placeholderData: previous => previous,
  });
}

export function useEvaluate() {
  return useMutation({
    mutationFn: (body: EvaluateRequest) => evaluate(body),
  });
}
