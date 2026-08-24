import { PageHeader } from '@/components/shared';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { AdvisoriesTab } from './_components/advisories-tab';
import { TriggerEventsTab } from './_components/trigger-events-tab';

interface AuditPageProps {
  searchParams: Promise<{ trigger_event_id?: string }>;
}

export default async function AuditPage({ searchParams }: AuditPageProps) {
  const { trigger_event_id } = await searchParams;
  const defaultTab = trigger_event_id ? 'trigger-events' : 'advisories';

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 px-6 py-12">
      <PageHeader
        title="Audit"
        description="Advisories are what Ankur said. Trigger events are every evaluation, including silent abstains."
      />
      <Tabs defaultValue={defaultTab}>
        <TabsList>
          <TabsTrigger value="advisories">Advisories</TabsTrigger>
          <TabsTrigger value="trigger-events">Trigger events</TabsTrigger>
        </TabsList>
        <TabsContent value="advisories">
          <AdvisoriesTab />
        </TabsContent>
        <TabsContent value="trigger-events">
          <TriggerEventsTab highlightId={trigger_event_id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
