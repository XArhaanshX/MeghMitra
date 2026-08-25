'use client';

import { useTheme } from 'next-themes';

import { useMounted } from '@/hooks/use-mounted';

// Styled as the plain-text "light mode" / "dark mode" label from the design
// reference rather than an icon switch -- clicking the label toggles theme.
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();

  if (!mounted) {
    return <span className="font-mono text-xs text-ink-soft">light mode</span>;
  }

  const isDark = resolvedTheme === 'dark';

  return (
    <button
      type="button"
      aria-label="Toggle theme"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      className="font-mono text-xs text-ink-soft transition-colors hover:text-ink"
    >
      {isDark ? 'dark mode' : 'light mode'}
    </button>
  );
}
