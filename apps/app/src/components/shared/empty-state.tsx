import type { ReactNode } from 'react';

interface EmptyStateProps {
  /** What is absent, stated plainly. */
  message: string;
  /** Why it may be absent, or what to do next. */
  hint?: string;
  action?: ReactNode;
}

// An empty result is usually a real answer about the corpus ("this state has
// no ingested plan"), not a failure. Say which, and give the reader a way
// forward, instead of a bare one-word placeholder.
export function EmptyState({ message, hint, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-sm border-2 border-dashed border-sand-300 bg-sand-50/60 px-6 py-12 text-center">
      <p className="font-mono text-sm font-bold text-ink">{message}</p>
      {hint && <p className="max-w-md text-sm text-ink-soft">{hint}</p>}
      {action}
    </div>
  );
}
