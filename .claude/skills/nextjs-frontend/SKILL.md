---
name: nextjs-frontend
description: Working in apps/app/ (the Next.js dashboard) -- new pages, components, API integration, or state. Use this for how apps/app talks to apps/api specifically; defer to apps/app/AGENTS.md and apps/app/CLAUDE.md for general Next.js/React/Tailwind/shadcn conventions in that project.
---

# Next.js dashboard (`apps/app/`)

`apps/app` is a separate pnpm-managed project (its own `package.json`, `AGENTS.md`, `CLAUDE.md`)
scaffolded from a general-purpose Next.js template. **Read `apps/app/AGENTS.md` for the full
stack/directory-structure reference** (TanStack Query, Zustand, shadcn/ui, React Hook Form,
etc.) -- this skill only covers the Ankur-specific integration points that template doesn't know
about.

## Talking to `apps/api`

- Base URL: `NEXT_PUBLIC_API_URL` (see `apps/app/src/env.ts`, validated via `@t3-oss/env-nextjs`
  -- never read `process.env` directly elsewhere). Local dev value is `http://localhost:8000`
  (`apps/api`'s default port, see `make dev`).
- HTTP client: `apps/app/src/api/client.ts` (`api`, an `axios` instance with error normalization
  via `toApiError`). Add new API calls in `apps/app/src/api/`, typed against the response
  shapes documented in `docs/api.md` -- do not hand-roll `fetch()` calls elsewhere.
- Response shapes mirror `ankur_schemas` models 1:1 (`DACPRule`, `Citation`,
  `DocumentMetadata`, etc. -- see `docs/domain-model.md`). If you add a Zod schema in
  `apps/app/src/schemas/` for a response, keep field names/nullability identical to the Python
  Pydantic model it mirrors; do not "clean up" nullability on the frontend (a `null` field means
  the DACP document didn't specify it -- surface that in the UI, don't hide or default it).
- Use TanStack Query (already wired via `query-provider.tsx`) for all API reads; this is the
  template's existing convention, not new for Ankur.

## Priority screens for the hackathon demo (build in this order if asked for "the dashboard")

1. **Rule browser** — `GET /rules` (optionally `?review_status=`), list view surfacing
   `fields.crop`, `fields.condition`, `fields.action`, `review_status`, and a link to the
   citation.
2. **Citation viewer** — `GET /rules/{id}/citation`; this is the "why did Ankur produce this
   recommendation?" view and is the single most important UI element for demoing the product's
   core claim (traceability to the source DACP page).
3. **Review queue** — `GET /review-queue` + `POST /rules/{id}/approve` /
   `POST /rules/{id}/reject`. Surface `confidence` and `notes` prominently -- a reviewer needs
   to see *why* a rule was flagged, not just that it was.

Do not build a document upload UI or a weather/trigger-engine view for this prototype -- both
are explicitly out of scope (see root `AGENTS.md` and `README.md`).

## Running

```bash
cd apps/app
pnpm install
pnpm dev            # expects apps/api running on NEXT_PUBLIC_API_URL, or requests will error
pnpm test
pnpm lint
```
