'use client';

import { useState, type FormEvent } from 'react';
import { toast } from 'sonner';

import { isApiError } from '@/api';
import { useEvaluate } from '@/api/advisories-hooks';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { evaluateRequestSchema } from '@/schemas';
import type { EvaluateRequest, EvaluateResponse } from '@/schemas';

import { PresetBar } from './preset-bar';
import { EVALUATE_PRESETS } from './presets';

interface EvaluateFormProps {
  onResult: (result: EvaluateResponse) => void;
}

// Presets fill the body but never hide it -- judges see and can edit the
// exact JSON that goes to POST /advisories, matching the documented contract.
export function EvaluateForm({ onResult }: EvaluateFormProps) {
  const [json, setJson] = useState(() => JSON.stringify(EVALUATE_PRESETS[0].request, null, 2));
  const [parseError, setParseError] = useState<string | null>(null);
  const evaluate = useEvaluate();

  function applyPreset(request: EvaluateRequest) {
    setJson(JSON.stringify(request, null, 2));
    setParseError(null);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();

    let parsed: unknown;
    try {
      parsed = JSON.parse(json);
    } catch {
      setParseError('Invalid JSON.');
      return;
    }

    const result = evaluateRequestSchema.safeParse(parsed);
    if (!result.success) {
      setParseError(
        result.error.issues
          .map(issue => `${issue.path.join('.') || 'body'}: ${issue.message}`)
          .join('; ')
      );
      return;
    }
    setParseError(null);

    try {
      onResult(await evaluate.mutateAsync(result.data));
    } catch (error) {
      toast.error(isApiError(error) ? error.message : 'Evaluation failed.');
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <PresetBar presets={EVALUATE_PRESETS} onSelect={preset => applyPreset(preset.request)} />
      <Textarea
        value={json}
        onChange={event => setJson(event.target.value)}
        rows={18}
        className="font-mono text-xs"
        aria-label="Evaluation request body"
      />
      {parseError && <p className="text-sm text-destructive">{parseError}</p>}
      <Button type="submit" disabled={evaluate.isPending}>
        {evaluate.isPending ? 'Evaluating…' : 'Run evaluation'}
      </Button>
    </form>
  );
}
