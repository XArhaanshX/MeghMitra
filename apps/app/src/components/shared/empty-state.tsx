interface EmptyStateProps {
  message: string;
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="rounded-sm border border-dashed border-sand-300 bg-sand-50/60 py-12 text-center font-mono text-sm text-ink-soft">
      {message}
    </div>
  );
}
