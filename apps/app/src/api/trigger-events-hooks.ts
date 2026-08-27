'use client';

import { useQuery } from '@tanstack/react-query';

import { listTriggerEvents, listTriggerEventsPage, triggerEventKeys } from './trigger-events';

export function useTriggerEvents() {
  return useQuery({
    queryKey: triggerEventKeys.lists(),
    queryFn: listTriggerEvents,
  });
}

export function useTriggerEventsPage(page: { limit: number; offset: number }) {
  return useQuery({
    queryKey: triggerEventKeys.list(page),
    queryFn: () => listTriggerEventsPage(page),
    placeholderData: previous => previous,
  });
}
