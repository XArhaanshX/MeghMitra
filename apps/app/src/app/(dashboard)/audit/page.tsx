import { PageHeader } from '@/components/shared';

import { AuditTabs } from './_components/audit-tabs';

interface AuditPageProps {
  searchParams: Promise<{ trigger_event_id?: string }>;
}

export default async function AuditPage({ searchParams }: AuditPageProps) {
  const { trigger_event_id } = await searchParams;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 px-6 py-10 sm:px-8 lg:py-14">
      <PageHeader
        title="Audit"
        description="Advisories issued are what the system said out loud. All evaluations includes the ones where it stayed silent, so a withheld recommendation is as traceable as a given one."
      />
      <AuditTabs
        highlightId={trigger_event_id}
        fallbackTab={trigger_event_id ? 'trigger-events' : 'advisories'}
      />
    </div>
  );
}
