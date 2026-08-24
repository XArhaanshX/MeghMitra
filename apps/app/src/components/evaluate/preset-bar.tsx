'use client';

import { Button } from '@/components/ui/button';
import type { EvaluateRequest } from '@/schemas';

export interface EvaluatePreset {
  id: string;
  label: string;
  description: string;
  request: EvaluateRequest;
}

interface PresetBarProps {
  presets: EvaluatePreset[];
  onSelect: (preset: EvaluatePreset) => void;
}

export function PresetBar({ presets, onSelect }: PresetBarProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {presets.map(preset => (
        <Button
          key={preset.id}
          type="button"
          variant="outline"
          size="sm"
          title={preset.description}
          onClick={() => onSelect(preset)}
        >
          {preset.label}
        </Button>
      ))}
    </div>
  );
}
