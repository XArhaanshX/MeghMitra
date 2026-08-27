import { PageHeader } from '@/components/shared';

import { EvaluatePanel } from './_components/evaluate-panel';

export default function EvaluatePage() {
  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-6 py-10 sm:px-8 lg:py-14">
      <PageHeader
        title="Evaluate"
        description="Send a weather observation to POST /advisories and see what comes back: either a cited rule to act on, or an abstention with the reason it was withheld."
        meta="This is not a forecast product. It demonstrates the retrieval contract."
      />
      <EvaluatePanel />
    </div>
  );
}
