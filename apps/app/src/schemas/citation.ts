import * as z from 'zod';

// Mirrors ankur_schemas.citation.Citation. `document`/`page` are required by the
// Pydantic type, but the domain invariant (`has_valid_citation`) also requires a
// non-blank document and page >= 1 -- callers must check that, not just presence.
export const citationSchema = z.object({
  document: z.string(),
  page: z.number().int(),
  source_text: z.string().nullable(),
  bounding_region: z.string().nullable(),
});
export type Citation = z.infer<typeof citationSchema>;

// ankur_domain.policies.has_valid_citation: a non-blank document and page >= 1.
// The only client-side guard allowed for the approval gate -- disable the
// affordance, never bypass the server-side `POST /rules/{id}/approve` check.
export function hasValidCitation(citation: Citation): boolean {
  return citation.document.trim().length > 0 && citation.page >= 1;
}
