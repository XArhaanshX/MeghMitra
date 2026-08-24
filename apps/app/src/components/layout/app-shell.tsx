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
    <div className="flex min-h-full flex-col">
      <header className="border-b">
        {/* Two rows below sm: nav needs its own full-width row or it overflows
            the viewport next to the logo -- three items in one row only fits
            once there's room (sm and up). */}
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center justify-between gap-4">
            <Link href="/" className="flex flex-col leading-tight">
              <span className="text-lg font-semibold tracking-tight">Ankur</span>
              <span className="text-xs text-muted-foreground">
                DACP contingency retrieval — Sirsa
              </span>
            </Link>
            <div className="flex items-center gap-3 sm:hidden">
              <HealthPill />
              <ThemeToggle />
            </div>
          </div>
          <Nav />
          <div className="hidden items-center gap-3 sm:flex">
            <HealthPill />
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}
