'use client';

import { useState } from 'react';

import { EvaluateForm, EvaluateResult } from '@/components/evaluate';
import type { EvaluateResponse } from '@/schemas';

export function EvaluatePanel() {
  const [result, setResult] = useState<EvaluateResponse | null>(null);

  return (
    <div className="space-y-8">
      <EvaluateForm onResult={setResult} />
      {/* One polite live region around the whole result: submitting replaces
          content far below the button, which a screen reader would otherwise
          never announce. */}
      <section aria-live="polite" aria-label="Evaluation result">
        {result && <EvaluateResult result={result} />}
      </section>
    </div>
  );
}
