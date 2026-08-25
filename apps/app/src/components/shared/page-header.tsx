import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="space-y-1.5">
        <h1 className="font-heading text-3xl font-bold tracking-tight text-ink">{title}</h1>
        {description && <p className="max-w-2xl text-ink-muted">{description}</p>}
      </div>
      {actions}
    </div>
  );
}
