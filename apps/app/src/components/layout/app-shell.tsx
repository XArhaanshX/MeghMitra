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
      <aside className="flex w-full shrink-0 flex-col justify-between border-b-2 border-sidebar-border bg-sidebar lg:sticky lg:top-0 lg:h-screen lg:w-[258px] lg:border-r-2 lg:border-b-0">
        <div>
          <Link href="/" className="block px-6 py-8">
            <span className="font-mono text-lg font-bold tracking-tight text-ink">ANKUR</span>
            <p className="mt-1 font-mono text-xs text-ink-soft">advisory retrieval, not advice</p>
          </Link>
          <Nav />
        </div>
        <div className="space-y-4 px-6 py-6">
          <div className="h-px bg-sand-300" />
          <HealthPill />
          <ThemeToggle />
        </div>
      </aside>
      <main className="min-w-0 flex-1 bg-background">{children}</main>
    </div>
  );
}
