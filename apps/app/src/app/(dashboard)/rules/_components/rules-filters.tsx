'use client';

import { parseAsBoolean, parseAsString, parseAsStringEnum, useQueryStates } from 'nuqs';

import { useStateDistricts, useStates } from '@/api/geo-hooks';
import { REVIEW_STATUS_LABEL } from '@/components/rules';
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
// it always agree on parsing/defaults. No default for `state`/`district` --
// omitted means national, matching the API's own "no state filter = every
// state" contract. A hardcoded default here previously snapped every fresh
// load and every cleared filter back to Sirsa/Haryana, which is exactly the
// Haryana-first behavior this filter must not have.
export const rulesFilterParsers = {
  review_status: parseAsStringEnum(STATUS_OPTIONS),
  state: parseAsString,
  district: parseAsString,
  advisory_eligible: parseAsBoolean,
};

export function RulesFilters() {
  const [filters, setFilters] = useQueryStates(rulesFilterParsers);
  const { data: states, isPending: statesPending } = useStates();
  const { data: districts, isPending: districtsPending } = useStateDistricts(
    filters.state ?? undefined
  );

  return (
    <div className="flex flex-wrap items-end gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rules-state">State</Label>
        <Select
          value={filters.state ?? ALL_VALUE}
          onValueChange={value =>
            // Changing state invalidates whatever district was selected under
            // the previous state -- clear it rather than leave a stale filter
            // silently scoped to a district that no longer applies.
            void setFilters({ state: value === ALL_VALUE ? null : value, district: null })
          }
        >
          <SelectTrigger id="rules-state" className="w-56" disabled={statesPending}>
            <SelectValue placeholder="All states" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_VALUE}>All states (India)</SelectItem>
            {states
              ?.filter(state => state.has_dacp_coverage)
              .map(state => (
                <SelectItem key={state.state_code} value={state.name}>
                  {state.name}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rules-district">District</Label>
        <Select
          value={filters.district ?? ALL_VALUE}
          onValueChange={value => void setFilters({ district: value === ALL_VALUE ? null : value })}
          disabled={!filters.state}
        >
          <SelectTrigger id="rules-district" className="w-56" disabled={districtsPending}>
            <SelectValue placeholder={filters.state ? 'All districts' : 'Select a state first'} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_VALUE}>All districts</SelectItem>
            {districts?.map(district => (
              <SelectItem key={district.district_code} value={district.name}>
                {district.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
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
