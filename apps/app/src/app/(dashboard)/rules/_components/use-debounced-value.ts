import { useEffect, useState } from 'react';

// Delays propagating a fast-changing value (e.g. keystrokes) until it settles
// for `delayMs`. Only the query-key input is debounced -- the district
// <Input>'s displayed value stays bound to the immediate URL state.
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timeout = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timeout);
  }, [value, delayMs]);

  return debounced;
}
