'use client';

import { useQuery } from '@tanstack/react-query';

import { coverageKeys, geoKeys, getCoverage, listStateDistricts, listStates } from './geo';

export function useStates() {
  return useQuery({
    queryKey: geoKeys.list(),
    queryFn: listStates,
  });
}

export function useStateDistricts(stateCode: string | undefined) {
  return useQuery({
    queryKey: [...geoKeys.all(), 'districts', stateCode] as const,
    queryFn: () => listStateDistricts(stateCode as string),
    enabled: stateCode !== undefined,
  });
}

export function useCoverage() {
  return useQuery({
    queryKey: coverageKeys.lists(),
    queryFn: getCoverage,
  });
}
