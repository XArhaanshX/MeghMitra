import { PageHeader } from '@/components/shared';

import { EvaluatePanel } from './_components/evaluate-panel';

export default function EvaluatePage() {
  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-6 py-12">
      <PageHeader
        title="Evaluate"
        description="Demo the retrieve-or-abstain decision against POST /advisories. Not a weather product -- a way to see the documented request/response contract."
      />
      <EvaluatePanel />
    </div>
  );
}
