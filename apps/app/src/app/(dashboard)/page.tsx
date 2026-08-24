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
    <div className="mx-auto w-full max-w-4xl space-y-10 px-6 py-16">
      <div className="space-y-3">
        <h1 className="text-4xl font-semibold tracking-tight">Ankur</h1>
        <p className="max-w-xl text-lg text-muted-foreground">
          Ankur retrieves the government-approved DACP contingency action that matches a detected
          field condition. It does not generate agricultural advice.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Advisory-eligible rules
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-semibold tabular-nums">{eligibleCount ?? '—'}</p>
            <p className="text-sm text-muted-foreground">Approved and cited, ready to trigger.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              In review queue
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-semibold tabular-nums">{reviewCount ?? '—'}</p>
            <p className="text-sm text-muted-foreground">Flagged for human review.</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-wrap gap-3">
        <Link href="/review" className={cn(buttonVariants({ variant: 'default' }))}>
          Open review queue
        </Link>
        <Link href="/evaluate" className={cn(buttonVariants({ variant: 'outline' }))}>
          Evaluate a condition
        </Link>
      </div>
    </div>
  );
}
