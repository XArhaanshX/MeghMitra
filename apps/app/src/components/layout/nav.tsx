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
    <nav className="flex flex-col gap-1 px-2 py-2 lg:flex-col">
      {LINKS.map(link => {
        const active = link.href === '/' ? pathname === '/' : pathname.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={cn(
              'flex h-12 items-center gap-3 rounded-[10px] px-4 font-mono text-sm transition-colors',
              active
                ? 'bg-sidebar-accent font-bold text-sidebar-accent-foreground'
                : 'text-sidebar-foreground hover:bg-sidebar-accent/40'
            )}
          >
            <span
              className={cn(
                'h-5 w-1 shrink-0 rounded-full',
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
