import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  /** Mono uppercase kicker above the title, e.g. a section or region label. */
  eyebrow?: string;
  /** Short factual line under the description, e.g. a result count. */
  meta?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({
  title,
  description,
  eyebrow,
  meta,
  actions,
}: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4 border-b-2 border-ink pb-5">
      <div className="min-w-0 space-y-2">
        {eyebrow && (
          <p className="font-mono text-xs font-bold tracking-widest text-teal-deep uppercase">
            {eyebrow}
          </p>
        )}
        <h1 className="font-heading text-3xl font-bold tracking-tight text-ink">{title}</h1>
        {description && <p className="max-w-2xl text-ink-muted">{description}</p>}
        {meta && <div className="font-mono text-xs text-ink-soft">{meta}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-3">{actions}</div>}
    </header>
  );
}
