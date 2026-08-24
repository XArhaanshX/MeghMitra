'use client';

import { useQuery } from '@tanstack/react-query';

import { getHealth, healthKey } from './health';

// Backs the shell's connection pill -- poll frequently, never retry a
// failure into a false "up" state, and let a rejected fetch mean "down".
export function useHealth() {
  return useQuery({
    queryKey: healthKey,
    queryFn: getHealth,
    refetchInterval: 15_000,
    retry: false,
  });
}
