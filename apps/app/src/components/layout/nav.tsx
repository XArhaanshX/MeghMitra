'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { cn } from '@/lib/utils';

const LINKS = [
  { href: '/', label: 'Home' },
  { href: '/rules', label: 'Rules' },
  { href: '/review', label: 'Review' },
  { href: '/evaluate', label: 'Evaluate' },
  { href: '/audit', label: 'Audit' },
];

export function Nav() {
  const pathname = usePathname();

  return (
    // Mobile lays the links out as one horizontally scrollable row, so the
    // nav costs about 48px of height instead of the ~400px a stacked sidebar
    // spent before any page content. Desktop keeps the sidebar column.
    <nav
      aria-label="Main"
      className="flex flex-row gap-1 overflow-x-auto border-t-2 border-sidebar-border px-2 lg:flex-col lg:overflow-visible lg:border-t-0 lg:py-2"
    >
      {LINKS.map(link => {
        const active = link.href === '/' ? pathname === '/' : pathname.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'flex h-12 shrink-0 items-center gap-3 border-b-2 px-4 font-mono text-sm whitespace-nowrap transition-colors lg:rounded-[10px] lg:border-b-0',
              active
                ? 'border-sidebar-primary font-bold text-sidebar-accent-foreground lg:border-transparent lg:bg-sidebar-accent'
                : 'border-transparent text-sidebar-foreground hover:bg-sidebar-accent/40'
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                'hidden h-5 w-1 shrink-0 rounded-full lg:block',
                active ? 'bg-sidebar-primary' : 'bg-transparent'
              )}
            />
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
