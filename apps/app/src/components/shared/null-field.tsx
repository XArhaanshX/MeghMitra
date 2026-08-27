import { cn } from '@/lib/utils';

interface NullFieldProps {
  label: string;
  value: string | null;
}

// Nulls are a documented DACP source gap, not a rendering bug -- always show
// them explicitly instead of hiding the row or defaulting to a guessed value.
// The border weight itself carries meaning: a heavy ink border marks a field
// the source document actually specified; a thin muted border marks a gap.
export function NullField({ label, value }: NullFieldProps) {
  return (
    <div
      className={cn(
        'rounded-sm px-4 py-3',
        value ? 'border-2 border-ink bg-sand-50' : 'border border-sand-300 bg-sand-50/60'
      )}
    >
      <p className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">{label}</p>
      <p
        className={cn(
          'mt-1 font-mono text-sm',
          value ? 'font-bold text-ink' : 'text-ink-soft italic'
        )}
      >
        {value ?? 'Not in source'}
      </p>
    </div>
  );
}
