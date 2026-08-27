import { Button } from '@/components/ui/button';

interface ErrorStateProps {
  /** What failed to load, in the reader's terms. */
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({ message = 'This section could not load.', onRetry }: ErrorStateProps) {
  return (
    // role="alert" so a failure that appears after load is announced rather
    // than silently swapped in below the fold.
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-sm border-2 border-destructive bg-destructive/10 px-6 py-8 text-center"
    >
      <p className="font-mono text-sm font-bold text-destructive-foreground">{message}</p>
      <p className="max-w-md text-sm text-ink-muted">
        The API may be unreachable. Check the status indicator in the sidebar, then try again.
      </p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
