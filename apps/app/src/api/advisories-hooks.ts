'use client';

import { useMutation, useQuery } from '@tanstack/react-query';

import type { EvaluateRequest } from '@/schemas';

import { advisoryKeys, evaluate, listAdvisories } from './advisories';

export function useAdvisories() {
  return useQuery({
    queryKey: advisoryKeys.lists(),
    queryFn: listAdvisories,
  });
}

export function useEvaluate() {
  return useMutation({
    mutationFn: (body: EvaluateRequest) => evaluate(body),
  });
}
