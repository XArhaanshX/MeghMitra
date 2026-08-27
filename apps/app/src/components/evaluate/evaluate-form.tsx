'use client';

import { useState, type FormEvent } from 'react';
import { toast } from 'sonner';

import { isApiError } from '@/api';
import { useEvaluate } from '@/api/advisories-hooks';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { evaluateRequestSchema } from '@/schemas';
import type { EvaluateResponse } from '@/schemas';

import { PresetBar } from './preset-bar';
import { EVALUATE_PRESETS } from './presets';

interface EvaluateFormProps {
  onResult: (result: EvaluateResponse) => void;
}

function bodyFor(presetId: string) {
  const preset = EVALUATE_PRESETS.find(entry => entry.id === presetId) ?? EVALUATE_PRESETS[0];
  return JSON.stringify(preset.request, null, 2);
}

// Presets fill the body but never hide it: the exact JSON that goes to
// POST /advisories stays visible and editable, matching the documented
// contract.
export function EvaluateForm({ onResult }: EvaluateFormProps) {
  const [presetId, setPresetId] = useState(EVALUATE_PRESETS[0].id);
  const [json, setJson] = useState(() => bodyFor(EVALUATE_PRESETS[0].id));
  const [parseError, setParseError] = useState<string | null>(null);
  const evaluate = useEvaluate();

  const edited = json !== bodyFor(presetId);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();

    let parsed: unknown;
    try {
      parsed = JSON.parse(json);
    } catch {
      setParseError('This is not valid JSON. Check for a trailing comma or an unquoted key.');
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
      toast.error(isApiError(error) ? error.message : 'The evaluation request failed.');
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <PresetBar
        presets={EVALUATE_PRESETS}
        activeId={presetId}
        onSelect={preset => {
          setPresetId(preset.id);
          setJson(bodyFor(preset.id));
          setParseError(null);
        }}
      />

      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Label htmlFor="evaluate-body">Request body sent to POST /advisories</Label>
          {edited && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setJson(bodyFor(presetId));
                setParseError(null);
              }}
            >
              Restore scenario
            </Button>
          )}
        </div>
        <Textarea
          id="evaluate-body"
          value={json}
          onChange={event => setJson(event.target.value)}
          rows={18}
          spellCheck={false}
          className="font-mono text-xs"
          aria-invalid={parseError !== null}
          aria-describedby={parseError ? 'evaluate-body-error' : undefined}
        />
        {parseError && (
          <p id="evaluate-body-error" role="alert" className="text-sm text-destructive-foreground">
            {parseError}
          </p>
        )}
      </div>

      <Button type="submit" disabled={evaluate.isPending}>
        {evaluate.isPending ? 'Evaluating' : 'Run evaluation'}
      </Button>
    </form>
  );
}
