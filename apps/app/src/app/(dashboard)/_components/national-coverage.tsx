import Link from 'next/link';

import { getCoverage, listStates } from '@/api/geo';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

// Server-rendered, same "never let a down API crash the landing page"
// contract as the rest of this dashboard: a failed fetch degrades to `null`,
// not a thrown error, and the section renders nothing rather than a broken
// shell.
async function safeFetch<T>(fetch: () => Promise<T>): Promise<T | null> {
  try {
    return await fetch();
  } catch {
    return null;
  }
}

const NUMBER_FORMAT = new Intl.NumberFormat('en-IN');

// No literal India map here: there is no per-block geometry ingested yet
// (`blocks.geom` is unpopulated; see ARCHITECTURE.md), so a geographic
// choropleth would need either external tile infrastructure this project
// does not have or a fabricated boundary dataset. A per-state table sorted
// by document count answers "which states does Ankur actually cover" with
// data that is genuinely live.
export async function NationalCoverage() {
  const [coverage, states] = await Promise.all([safeFetch(getCoverage), safeFetch(listStates)]);

  if (coverage === null && states === null) return null;

  const coveredStates = (states ?? [])
    .filter(state => state.has_dacp_coverage)
    .sort((a, b) => b.document_count - a.document_count);
  const uncoveredCount = (states ?? []).filter(state => !state.has_dacp_coverage).length;
  const classifiedFraction =
    coverage && coverage.rules > 0 ? 1 - coverage.unmapped_rules / coverage.rules : 0;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b-2 border-ink pb-3">
        <h2 className="font-heading text-2xl font-bold text-ink">National coverage</h2>
        <Link
          href="/rules"
          className="font-mono text-xs font-bold tracking-widest text-teal-deep uppercase hover:underline"
        >
          Browse all rules
        </Link>
      </div>

      {coverage && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryStat label="States and UTs" value={NUMBER_FORMAT.format(coveredStates.length)} />
          <SummaryStat label="Plans ingested" value={NUMBER_FORMAT.format(coverage.documents)} />
          <SummaryStat label="Rules extracted" value={NUMBER_FORMAT.format(coverage.rules)} />
          <SummaryStat
            label="Conditions classified"
            value={`${(classifiedFraction * 100).toFixed(0)}%`}
            hint={`${NUMBER_FORMAT.format(coverage.unmapped_rules)} rules unmapped`}
          />
        </div>
      )}

      {states && coveredStates.length > 0 && (
        <div className="rounded-lg border-2 border-ink bg-sand-50">
          <div className="border-b-2 border-ink px-4 py-3">
            <h3 className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">
              Ingested plans by state
            </h3>
          </div>
          {/* Capped height with the header pinned: the full national footprint
              stays visible and scannable without pushing the rest of the page
              down by thirty rows. */}
          <div className="max-h-80 overflow-y-auto">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-sand-100">
                <TableRow>
                  <TableHead>State</TableHead>
                  <TableHead className="text-right">Districts</TableHead>
                  <TableHead className="text-right">Plans</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {coveredStates.map(state => (
                  <TableRow key={state.state_code}>
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
                    <TableCell className="text-right tabular-nums">
                      {NUMBER_FORMAT.format(state.district_count)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {NUMBER_FORMAT.format(state.document_count)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {uncoveredCount > 0 && (
            <p className="border-t-2 border-ink px-4 py-3 text-sm text-ink-soft">
              {uncoveredCount} more {uncoveredCount === 1 ? 'state or union territory has' : 'states and union territories have'}{' '}
              no ingested plan yet. They are reported as absent rather than filled with estimates.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function SummaryStat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border-2 border-ink bg-sand-50 p-4">
      <p className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">{label}</p>
      <p className="mt-2 font-heading text-3xl font-bold text-ink tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}
