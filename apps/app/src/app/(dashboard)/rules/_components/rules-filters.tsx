'use client';

import { debounce, parseAsBoolean, parseAsString, parseAsStringEnum, useQueryStates } from 'nuqs';

import { REVIEW_STATUS_LABEL } from '@/components/rules';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { reviewStatusSchema } from '@/schemas';

const ALL_VALUE = 'all';
const STATUS_OPTIONS = reviewStatusSchema.options;

// Shared with rules-table.tsx so the filter bar and the fetch that reacts to
// it always agree on parsing/defaults. District is debounced -- typed on
// every keystroke otherwise, which both spams the network and (via
// `.withDefault`) snaps back to "Sirsa" mid-clear if sent as `null`.
export const rulesFilterParsers = {
  review_status: parseAsStringEnum(STATUS_OPTIONS),
  district: parseAsString.withDefault('Sirsa').withOptions({ limitUrlUpdates: debounce(400) }),
  advisory_eligible: parseAsBoolean,
};

export function RulesFilters() {
  const [filters, setFilters] = useQueryStates(rulesFilterParsers);

  return (
    <div className="flex flex-wrap items-end gap-4">
      <div className="space-y-1.5">
        <Label htmlFor="rules-district">District</Label>
        <Input
          id="rules-district"
          value={filters.district}
          onChange={event => void setFilters({ district: event.target.value })}
          className="w-40"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="rules-status">Review status</Label>
        <Select
          value={filters.review_status ?? ALL_VALUE}
          onValueChange={value => {
            const parsed = reviewStatusSchema.safeParse(value).data;
            void setFilters({ review_status: value === ALL_VALUE ? null : (parsed ?? null) });
          }}
        >
          <SelectTrigger id="rules-status" className="w-48">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_VALUE}>All statuses</SelectItem>
            {STATUS_OPTIONS.map(status => (
              <SelectItem key={status} value={status}>
                {REVIEW_STATUS_LABEL[status]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <label className="flex items-center gap-2 pb-2 font-mono text-sm text-ink">
        <input
          type="checkbox"
          checked={filters.advisory_eligible ?? false}
          onChange={event => void setFilters({ advisory_eligible: event.target.checked || null })}
          className="size-4 rounded-sm border-2 border-ink accent-teal"
        />
        Advisory-eligible only
      </label>
    </div>
  );
}
