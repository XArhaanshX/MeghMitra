'use client';

import { useQuery } from '@tanstack/react-query';

import { listTriggerEvents, triggerEventKeys } from './trigger-events';

export function useTriggerEvents() {
  return useQuery({
    queryKey: triggerEventKeys.lists(),
    queryFn: listTriggerEvents,
  });
}
