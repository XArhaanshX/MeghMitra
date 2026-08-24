interface NullFieldProps {
  label: string;
  value: string | null;
}

// Nulls are a documented DACP source gap, not a rendering bug -- always show
// them explicitly instead of hiding the row or defaulting to a guessed value.
export function NullField({ label, value }: NullFieldProps) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
      <p className={value ? 'text-sm' : 'text-sm text-muted-foreground italic'}>
        {value ?? 'Not specified in source'}
      </p>
    </div>
  );
}
