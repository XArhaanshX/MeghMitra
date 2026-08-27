import type { ReactNode } from 'react';
import Link from 'next/link';

import { HealthPill } from './health-pill';
import { Nav } from './nav';
import { ThemeToggle } from './theme-toggle';

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex min-h-full flex-col lg:flex-row">
      <aside className="flex w-full shrink-0 flex-col border-b-2 border-sidebar-border bg-sidebar lg:sticky lg:top-0 lg:h-screen lg:w-[258px] lg:border-r-2 lg:border-b-0">
        {/* On mobile the wordmark and the status controls share one row; on
            desktop they return to opposite ends of the sidebar column. */}
        <div className="flex items-center justify-between gap-4 px-5 py-4 lg:block lg:px-6 lg:py-8">
          <Link href="/" className="block min-w-0">
            <span className="font-mono text-lg font-bold tracking-tight text-ink">ANKUR</span>
            <p className="mt-1 truncate font-mono text-xs text-ink-soft">
              advisory retrieval, not advice
            </p>
          </Link>
          <div className="flex shrink-0 items-center gap-3 lg:hidden">
            <HealthPill />
            <ThemeToggle />
          </div>
        </div>
        <Nav />
        <div className="mt-auto hidden space-y-4 px-6 py-6 lg:block">
          <div className="h-px bg-sand-300" />
          <HealthPill />
          <ThemeToggle />
        </div>
      </aside>
      <main className="min-w-0 flex-1 bg-background">{children}</main>
    </div>
  );
}
