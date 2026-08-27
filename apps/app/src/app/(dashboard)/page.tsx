import Link from 'next/link';

import { countReviewQueue } from '@/api/review';
import { countRules } from '@/api/rules';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { NationalCoverage } from './_components/national-coverage';

// Server-fetched via axios (not Next's `fetch()`), so Next's automatic
// dynamic-API detection never sees these calls and happily prerenders this
// page as static HTML at build time -- baking in whatever the API returned
// (or, in CI, couldn't return) at that moment forever. Force per-request
// rendering so the counts and NationalCoverage panel are always live.
export const dynamic = 'force-dynamic';

// Never let a down API crash the landing page -- the shell's status
// indicator already reports that; the counts fall back to "unavailable".
async function safeCount(fetchCount: () => Promise<number>): Promise<number | null> {
  try {
    return await fetchCount();
  } catch {
    return null;
  }
}

const NUMBER_FORMAT = new Intl.NumberFormat('en-IN');

export default async function HomePage() {
  // Exact totals from the pagination envelope. Counting the length of an
  // unpaginated list would cap at the API's default page size of 50.
  const [eligibleCount, reviewCount] = await Promise.all([
    safeCount(() => countRules({ advisoryEligible: true })),
    safeCount(countReviewQueue),
  ]);

  return (
    <div className="mx-auto w-full max-w-5xl space-y-10 px-6 py-10 sm:px-8 lg:px-12 lg:py-14">
      <section className="space-y-4">
        <p className="font-mono text-xs font-bold tracking-widest text-teal-deep uppercase">
          Ankur advisory system
        </p>
        <h1 className="max-w-2xl font-heading text-4xl leading-tight font-bold tracking-tight text-ink sm:text-5xl">
          Retrieves pre-approved actions across India. Never generates advice.
        </h1>
        <p className="max-w-xl text-ink-muted">
          Every recommendation is a lookup against a government-approved rule that carries a page
          citation. When no approved rule covers the detected condition, the system abstains rather
          than guessing.
        </p>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <StatLink
          href="/rules?advisory_eligible=true"
          label="Advisory-eligible rules"
          value={eligibleCount}
          caption="Approved, citation-backed, live in the retrieval index."
          tone="soft"
        />
        <StatLink
          href="/review"
          label="Awaiting review"
          value={reviewCount}
          caption="Ambiguous or low-confidence extractions held for a human decision."
          tone="strong"
        />
      </section>

      <NationalCoverage />

      <section className="flex flex-wrap items-center gap-4 border-t-2 border-ink pt-6">
        <Link href="/evaluate" className={cn(buttonVariants({ variant: 'default' }))}>
          Evaluate a condition
        </Link>
        <p className="text-sm text-ink-muted">
          Post a weather observation and watch the system retrieve a cited rule or abstain.
        </p>
      </section>
    </div>
  );
}

// The whole card is the link: a headline number that navigates to the list it
// counts, rather than a number and a separate button repeating the same
// destination.
function StatLink({
  href,
  label,
  value,
  caption,
  tone,
}: {
  href: string;
  label: string;
  value: number | null;
  caption: string;
  tone: 'soft' | 'strong';
}) {
  const strong = tone === 'strong';

  return (
    <Link
      href={href}
      className={cn(
        'group flex flex-col gap-3 rounded-lg border-2 border-ink p-6 transition-shadow hover:shadow-[4px_4px_0_0_var(--ink)] focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:outline-none',
        strong ? 'bg-teal text-sand-50' : 'bg-teal-soft'
      )}
    >
      <p
        className={cn(
          'font-mono text-xs font-bold tracking-widest uppercase',
          strong ? 'text-sand-50/80' : 'text-teal-deep'
        )}
      >
        {label}
      </p>
      <p
        className={cn(
          'font-heading text-4xl font-bold tabular-nums',
          strong ? 'text-sand-50' : 'text-ink'
        )}
      >
        {value === null ? 'Unavailable' : NUMBER_FORMAT.format(value)}
      </p>
      <p className={cn('text-sm', strong ? 'text-sand-50/80' : 'text-ink-muted')}>{caption}</p>
      <span
        className={cn(
          'mt-auto font-mono text-xs font-bold tracking-widest uppercase group-hover:underline',
          strong ? 'text-sand-50' : 'text-teal-deep'
        )}
      >
        View list
      </span>
    </Link>
  );
}
