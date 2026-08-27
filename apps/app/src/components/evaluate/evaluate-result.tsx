import Link from 'next/link';

import { CitationPanel } from '@/components/citation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { EvaluateResponse } from '@/schemas';

import { ActionChip } from './action-chip';

interface EvaluateResultProps {
  result: EvaluateResponse;
}

const PERCENT = (value: number) => `${(value * 100).toFixed(0)}%`;

export function EvaluateResult({ result }: EvaluateResultProps) {
  const abstained = result.action === 'abstain';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4 border-t-2 border-ink pt-6">
        <ActionChip action={result.action} />
        <div className="space-y-0.5">
          <p className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">
            Detected condition
          </p>
          <p className="text-sm text-ink">
            {result.detected_condition
              ? result.detected_condition.replaceAll('_', ' ')
              : 'No condition detected'}
          </p>
        </div>
      </div>

      {abstained && result.abstain_reasons.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Why no advisory was issued</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm text-ink-muted">
              {result.abstain_reasons.map(reason => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
            <p className="mt-3 text-sm text-ink-muted">
              Abstaining is a successful outcome. It means no approved rule covered this situation,
              so nothing was invented to fill the gap.
            </p>
          </CardContent>
        </Card>
      )}

      {result.rule && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Retrieved rule</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="text-ink">
              <span className="font-medium">{result.rule.fields.crop ?? 'Crop not in source'}</span>
              {result.rule.fields.action ? `: ${result.rule.fields.action}` : ''}
            </p>
            {result.rule.fields.variety && (
              <p className="text-ink-muted">Variety: {result.rule.fields.variety}</p>
            )}
            <Link
              href={`/rules/${result.rule.id}`}
              className="inline-block font-mono text-teal-deep hover:underline"
            >
              Open full rule
            </Link>
          </CardContent>
        </Card>
      )}

      <CitationPanel citation={result.citation} heading="Source for this decision" />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Decision detail</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">Probability</p>
            <p className="text-ink tabular-nums">{PERCENT(result.probability)}</p>
          </div>
          {result.threshold !== null && (
            <div>
              <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">Threshold</p>
              <p className="text-ink tabular-nums">{PERCENT(result.threshold)}</p>
            </div>
          )}
          {result.decision_reason && (
            <div className="sm:col-span-2">
              <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">Reason</p>
              <p className="text-ink">{result.decision_reason}</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Link
        href={`/audit?tab=trigger-events&trigger_event_id=${result.trigger_event_id}`}
        className="inline-block font-mono text-sm text-teal-deep hover:underline"
      >
        See this evaluation in the audit log
      </Link>
    </div>
  );
}
