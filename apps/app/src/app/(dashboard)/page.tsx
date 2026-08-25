import Link from 'next/link';

import { reviewQueue } from '@/api/review';
import { listRules } from '@/api/rules';
import { buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

// Never let a down API crash the landing page -- the shell's health pill
// already communicates that; the counts just fall back to a dash.
async function safeCount<T>(fetchList: () => Promise<T[]>): Promise<number | null> {
  try {
    return (await fetchList()).length;
  } catch {
    return null;
  }
}

export default async function HomePage() {
  const [eligibleCount, reviewCount] = await Promise.all([
    safeCount(() => listRules({ advisoryEligible: true })),
    safeCount(() => reviewQueue()),
  ]);

  return (
    <div className="mx-auto w-full max-w-5xl space-y-8 px-8 py-12 lg:px-12">
      <div className="space-y-4">
        <p className="font-mono text-xs font-bold tracking-widest text-teal-deep uppercase">
          Field Record advisory system
        </p>
        <h1 className="max-w-2xl font-heading text-4xl leading-tight font-bold tracking-tight text-ink sm:text-5xl">
          Retrieves pre-approved actions. Never generates advice.
        </h1>
        <p className="max-w-xl text-ink-muted">
          Every recommendation is a lookup against a pre-approved rule with a citation. If there is
          no eligible rule, the system abstains — it does not guess.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card className="bg-teal-soft">
          <CardHeader>
            <CardTitle className="font-mono text-xs font-bold tracking-widest text-teal-deep uppercase">
              Advisory-eligible rules
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-heading text-4xl font-bold text-ink tabular-nums">
              {eligibleCount ?? '—'}
            </p>
            <p className="mt-1 text-sm text-ink-muted">
              Approved rules with a valid citation, live in the retrieval index.
            </p>
          </CardContent>
        </Card>
        <Card className="bg-teal text-sand-50">
          <CardHeader>
            <CardTitle className="font-mono text-xs font-bold tracking-widest text-sand-50/80 uppercase">
              Review queue
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-heading text-4xl font-bold text-sand-50 tabular-nums">
              {reviewCount ?? '—'}
            </p>
            <p className="mt-1 text-sm text-sand-50/80">
              Low-confidence or ambiguous rules awaiting a human decision.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-wrap gap-3">
        <Link href="/review" className={cn(buttonVariants({ variant: 'default' }))}>
          Open review queue →
        </Link>
        <Link href="/evaluate" className={cn(buttonVariants({ variant: 'outline' }))}>
          Evaluate a condition
        </Link>
      </div>
    </div>
  );
}
