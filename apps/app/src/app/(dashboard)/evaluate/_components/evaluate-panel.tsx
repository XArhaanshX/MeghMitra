'use client';

import { useState } from 'react';

import { EvaluateForm, EvaluateResult } from '@/components/evaluate';
import type { EvaluateResponse } from '@/schemas';

export function EvaluatePanel() {
  const [result, setResult] = useState<EvaluateResponse | null>(null);

  return (
    <div className="space-y-8">
      <EvaluateForm onResult={setResult} />
      {result && <EvaluateResult result={result} />}
    </div>
  );
}
