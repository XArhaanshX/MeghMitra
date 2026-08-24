import Link from 'next/link';

import { CitationPanel } from '@/components/citation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { EvaluateResponse } from '@/schemas';

import { ActionChip } from './action-chip';

interface EvaluateResultProps {
  result: EvaluateResponse;
}

export function EvaluateResult({ result }: EvaluateResultProps) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <ActionChip action={result.action} />
        {result.detected_condition && (
          <span className="text-sm text-muted-foreground">
            Detected: {result.detected_condition.replaceAll('_', ' ')}
          </span>
        )}
      </div>

      {result.action === 'abstain' && result.abstain_reasons.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Why Ankur stayed silent</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
              {result.abstain_reasons.map(reason => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {result.rule && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Retrieved rule</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p>
              <span className="font-medium">{result.rule.fields.crop ?? 'Crop not specified'}</span>{' '}
              — {result.rule.fields.action ?? 'No action recorded'}
            </p>
            {result.rule.fields.variety && (
              <p className="text-muted-foreground">Variety: {result.rule.fields.variety}</p>
            )}
            <Link href={`/rules/${result.rule.id}`} className="text-primary hover:underline">
              View full rule
            </Link>
          </CardContent>
        </Card>
      )}

      <CitationPanel citation={result.citation} heading="Why Ankur said this" />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Decision detail</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
          <p>
            <span className="text-muted-foreground">Probability:</span>{' '}
            {(result.probability * 100).toFixed(0)}%
          </p>
          {result.threshold !== null && (
            <p>
              <span className="text-muted-foreground">Threshold:</span>{' '}
              {(result.threshold * 100).toFixed(0)}%
            </p>
          )}
          {result.decision_reason && (
            <p className="sm:col-span-2">
              <span className="text-muted-foreground">Reason:</span> {result.decision_reason}
            </p>
          )}
        </CardContent>
      </Card>

      <Link
        href={`/audit?trigger_event_id=${result.trigger_event_id}`}
        className="text-sm text-primary hover:underline"
      >
        View trigger event in audit log →
      </Link>
    </div>
  );
}
