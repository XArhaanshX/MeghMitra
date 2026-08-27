'use client';

import { cn } from '@/lib/utils';
import type { EvaluateRequest } from '@/schemas';

export interface EvaluatePreset {
  id: string;
  label: string;
  description: string;
  request: EvaluateRequest;
}

interface PresetBarProps {
  presets: EvaluatePreset[];
  activeId: string;
  onSelect: (preset: EvaluatePreset) => void;
}

export function PresetBar({ presets, activeId, onSelect }: PresetBarProps) {
  const active = presets.find(preset => preset.id === activeId);

  return (
    <div className="space-y-3">
      <p
        id="preset-group-label"
        className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase"
      >
        Scenario
      </p>
      <div role="group" aria-labelledby="preset-group-label" className="flex flex-wrap gap-2">
        {presets.map(preset => {
          const selected = preset.id === activeId;
          return (
            <button
              key={preset.id}
              type="button"
              // aria-pressed rather than a title tooltip: the selected
              // scenario is now conveyed to assistive tech and on touch,
              // where a title never appears at all.
              aria-pressed={selected}
              onClick={() => onSelect(preset)}
              className={cn(
                'rounded-sm border-2 border-ink px-3 py-1.5 font-mono text-xs transition-colors focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:outline-none',
                selected
                  ? 'bg-teal font-bold text-sand-50'
                  : 'bg-sand-50 text-ink hover:bg-teal-soft'
              )}
            >
              {preset.label}
            </button>
          );
        })}
      </div>
      {active && (
        // The description is on the page, not hidden in a tooltip: it states
        // what the scenario is meant to prove, which is the point of the demo.
        <p className="text-sm text-ink-muted">{active.description}</p>
      )}
    </div>
  );
}
