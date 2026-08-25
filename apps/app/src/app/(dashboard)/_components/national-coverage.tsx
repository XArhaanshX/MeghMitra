import Link from 'next/link';

import { getCoverage, listStates } from '@/api/geo';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { CoverageResponse, StateSummary } from '@/schemas';

// Server-rendered, same "never let a down API crash the landing page" contract
// as the rest of this dashboard -- a failed fetch degrades to `null`, not a
// thrown error, and the section renders nothing rather than a broken shell.
async function safeFetch<T>(fetch: () => Promise<T>): Promise<T | null> {
  try {
    return await fetch();
  } catch {
    return null;
  }
}

// No literal India map here -- there is no per-block geometry ingested yet
// (`blocks.geom` is unpopulated; see ARCHITECTURE.md), so a geographic
// choropleth would either need external tile infrastructure this project
// doesn't have or a fabricated boundary dataset. A per-state coverage table,
// sorted by document count, gives the same "which states does Ankur actually
// cover" answer honestly with data that is genuinely live.
export async function NationalCoverage() {
  const [coverage, states] = await Promise.all([safeFetch(getCoverage), safeFetch(listStates)]);

  if (coverage === null && states === null) return null;

  const coveredStates = (states ?? [])
    .filter(state => state.has_dacp_coverage)
    .sort((a, b) => b.document_count - a.document_count);
  const uncoveredCount = (states ?? []).filter(state => !state.has_dacp_coverage).length;

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-heading text-2xl font-bold text-ink">National coverage</h2>
        <Link href="/rules" className="text-sm text-teal-deep hover:underline">
          Browse all rules →
        </Link>
      </div>
      {coverage && <CoverageSummary coverage={coverage} statesCovered={coveredStates.length} />}
      {states && (
        <Card>
          <CardHeader>
            <CardTitle className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">
              Ingested plans by state
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>State</TableHead>
                  <TableHead>Districts ingested</TableHead>
                  <TableHead>Documents</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {coveredStates.map(state => (
                  <StateRow key={state.state_code} state={state} />
                ))}
              </TableBody>
            </Table>
            {uncoveredCount > 0 && (
              <p className="mt-3 font-mono text-xs text-ink-soft">
                {uncoveredCount} state{uncoveredCount === 1 ? '' : 's'}/UTs have no ingested DACP
                yet -- shown as absent, not guessed.
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StateRow({ state }: { state: StateSummary }) {
  return (
    <TableRow>
      <TableCell>
        <Link
          href={`/rules?state=${encodeURIComponent(state.name)}`}
          className="font-medium hover:underline"
        >
          {state.name}
        </Link>
        {state.kind === 'union_territory' && (
          <Badge variant="outline" className="ml-2">
            UT
          </Badge>
        )}
      </TableCell>
      <TableCell className="tabular-nums">{state.district_count}</TableCell>
      <TableCell className="tabular-nums">{state.document_count}</TableCell>
    </TableRow>
  );
}

function CoverageSummary({
  coverage,
  statesCovered,
}: {
  coverage: CoverageResponse;
  statesCovered: number;
}) {
  const mappedFraction = coverage.rules === 0 ? 0 : 1 - coverage.unmapped_rules / coverage.rules;
  return (
    <div className="grid gap-4 sm:grid-cols-4">
      <SummaryStat label="States/UTs covered" value={statesCovered} />
      <SummaryStat label="Documents ingested" value={coverage.documents} />
      <SummaryStat label="Rules extracted" value={coverage.rules} />
      <SummaryStat
        label="Condition mapped"
        value={`${(mappedFraction * 100).toFixed(0)}%`}
        hint={`${coverage.unmapped_rules} unmapped`}
      />
    </div>
  );
}

function SummaryStat({
  label,
  value,
  hint,
}: {
  label: string;
  value: number | string;
  hint?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="font-heading text-3xl font-bold text-ink tabular-nums">{value}</p>
        {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
      </CardContent>
    </Card>
  );
}
