'use client';

import { useQueryStates } from 'nuqs';

import { useStateDistricts, useStates } from '@/api/geo-hooks';
import { REVIEW_STATUS_LABEL } from '@/components/rules';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { reviewStatusSchema } from '@/schemas';

import { rulesFilterParsers } from './rules-query';

const ALL_VALUE = 'all';
const STATUS_OPTIONS = reviewStatusSchema.options;

// The subset of filter keys a chip may clear. Every one of them accepts
// `null` to mean "drop this from the URL".
type FilterReset = Partial<
  Record<'state' | 'district' | 'review_status' | 'advisory_eligible', null>
>;

export function RulesFilters() {
  const [filters, setFilters] = useQueryStates(rulesFilterParsers);
  const { data: states, isPending: statesPending } = useStates();
  // `/geo/states/{state_code}/districts` takes the state's short code, not
  // its display name. `filters.state` holds the name, since that is what
  // `GET /rules?state=` and the rule fields themselves use, so resolve name
  // to code here rather than changing what the URL contract stores.
  const selectedStateCode = states?.find(state => state.name === filters.state)?.state_code;
  const { data: districts, isPending: districtsPending } = useStateDistricts(selectedStateCode);

  // Clearing a chip nulls only the keys it owns; `page` is reset alongside
  // it at the call site, since any filter change invalidates the offset.
  const active: { key: string; label: string; clear: FilterReset }[] = [];
  if (filters.state) {
    active.push({
      key: 'state',
      label: filters.state,
      clear: { state: null, district: null },
    });
  }
  if (filters.district) {
    active.push({ key: 'district', label: filters.district, clear: { district: null } });
  }
  if (filters.review_status) {
    active.push({
      key: 'review_status',
      label: REVIEW_STATUS_LABEL[filters.review_status],
      clear: { review_status: null },
    });
  }
  if (filters.advisory_eligible) {
    active.push({
      key: 'advisory_eligible',
      label: 'Advisory-eligible only',
      clear: { advisory_eligible: null },
    });
  }

  return (
    <section aria-label="Filter rules" className="space-y-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rules-state">State</Label>
          <Select
            value={filters.state ?? ALL_VALUE}
            onValueChange={value =>
              // Changing state invalidates whatever district was selected
              // under the previous one, and any page beyond the first.
              void setFilters({
                state: value === ALL_VALUE ? null : value,
                district: null,
                page: null,
              })
            }
          >
            {/* Explicit children rather than letting Radix resolve the
                selected item's text: the items live in SelectContent, which
                is not mounted until the menu opens, so before the first open
                the trigger would otherwise display the raw value ("all"). */}
            <SelectTrigger id="rules-state" className="w-56" disabled={statesPending}>
              <SelectValue>{filters.state ?? 'All states'}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_VALUE}>All states</SelectItem>
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
            onValueChange={value =>
              void setFilters({ district: value === ALL_VALUE ? null : value, page: null })
            }
            disabled={!filters.state || districtsPending}
          >
            <SelectTrigger id="rules-district" className="w-56">
              <SelectValue>
                {filters.district ?? (filters.state ? 'All districts' : 'Choose a state first')}
              </SelectValue>
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
              void setFilters({
                review_status: value === ALL_VALUE ? null : (parsed ?? null),
                page: null,
              });
            }}
          >
            <SelectTrigger id="rules-status" className="w-48">
              <SelectValue>
                {filters.review_status ? REVIEW_STATUS_LABEL[filters.review_status] : 'All statuses'}
              </SelectValue>
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

        <div className="flex items-center gap-2 pb-2.5">
          <input
            id="rules-advisory-eligible"
            type="checkbox"
            checked={filters.advisory_eligible ?? false}
            onChange={event =>
              void setFilters({ advisory_eligible: event.target.checked || null, page: null })
            }
            className="size-4 rounded-sm border-2 border-ink accent-teal"
          />
          <Label htmlFor="rules-advisory-eligible" className="font-mono text-sm">
            Advisory-eligible only
          </Label>
        </div>
      </div>

      {active.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs font-bold tracking-widest text-ink-soft uppercase">
            Filtered by
          </span>
          {active.map(chip => (
            <button
              key={chip.key}
              type="button"
              onClick={() => void setFilters({ ...chip.clear, page: null })}
              className="inline-flex items-center gap-2 rounded-sm border-2 border-ink bg-teal-soft px-2.5 py-1 font-mono text-xs text-teal-deep transition-colors hover:bg-teal hover:text-sand-50"
            >
              {chip.label}
              <span aria-hidden="true" className="font-bold">
                x
              </span>
              <span className="sr-only">Remove this filter</span>
            </button>
          ))}
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              void setFilters({
                state: null,
                district: null,
                review_status: null,
                advisory_eligible: null,
                page: null,
              })
            }
          >
            Clear all
          </Button>
        </div>
      )}
    </section>
  );
}
