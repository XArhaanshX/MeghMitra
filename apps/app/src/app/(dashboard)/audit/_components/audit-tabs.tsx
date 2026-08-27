'use client';

import { parseAsStringLiteral, useQueryState } from 'nuqs';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { AdvisoriesTab } from './advisories-tab';
import { TriggerEventsTab } from './trigger-events-tab';

const TABS = ['advisories', 'trigger-events'] as const;

interface AuditTabsProps {
  highlightId?: string;
  /** Which tab to show when the URL does not name one. */
  fallbackTab: (typeof TABS)[number];
}

export function AuditTabs({ highlightId, fallbackTab }: AuditTabsProps) {
  // The selected tab lives in the URL so a reload, a back navigation, or a
  // shared link lands on the same view. Previously it was initial-render
  // state only, and refreshing silently snapped back to advisories.
  const [tab, setTab] = useQueryState(
    'tab',
    parseAsStringLiteral(TABS).withDefault(fallbackTab)
  );

  return (
    <Tabs value={tab} onValueChange={value => void setTab(value as (typeof TABS)[number])}>
      <TabsList>
        <TabsTrigger value="advisories">Advisories issued</TabsTrigger>
        <TabsTrigger value="trigger-events">All evaluations</TabsTrigger>
      </TabsList>
      <TabsContent value="advisories">
        <AdvisoriesTab />
      </TabsContent>
      <TabsContent value="trigger-events">
        <TriggerEventsTab highlightId={highlightId} />
      </TabsContent>
    </Tabs>
  );
}
