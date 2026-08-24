# Ankur — Agent Guide

Coding-agent reference for this repo. Read this first; it points at the deeper docs instead of
duplicating them. Keep it current when structure, invariants, or commands change.

## The one thing to never violate

> **Ankur does not generate agricultural advice.** It retrieves pre-approved government
> contingency actions from DACP documents and activates the one matching the detected
> condition.

Concretely, in code:

- Never invent a crop variety, seed rate, action, or citation. Missing source data stays `null`.
- Extraction (`document_intelligence`) never assigns `review_status = approved`. Only a human,
  via `POST /rules/{id}/approve`, does.
- `ankur_domain.policies.can_approve()` requires a valid citation, full stop -- this is enforced
  in Python *and* as a Postgres `CHECK` constraint. If you're touching approval logic, read
  `docs/domain-model.md` first.

Full rationale and the exact invariants: **`docs/domain-model.md`**.

## Repo map -> where to read more

| Area | Path | Docs |
|---|---|---|
| Data shapes (Pydantic) | `packages/schemas/` | `docs/domain-model.md` |
| Business rules, repository ports, services | `packages/domain/` | `docs/domain-model.md` |
| PDF -> structured rule pipeline | `services/document-intelligence/` | `docs/document-intelligence.md` |
| Weather -> moisture state -> condition -> advisory | `services/trigger-engine/` | `docs/ml-pipeline.md` |
| FastAPI service | `apps/api/` | `docs/api.md` |
| Next.js dashboard | `apps/app/` | `apps/app/AGENTS.md` (scoped, frontend-only) |
| Postgres schema/migrations | `db/migrations/` | `docs/database.md` |
| System diagram, layering, tech-choice rationale | -- | `docs/architecture.md` |
| Non-obvious decisions and why | -- | `docs/decisions.md` |
| Local setup, running everything | -- | `README.md` |

`apps/app` is a separate pnpm-managed Next.js project with its own `AGENTS.md` and `CLAUDE.md`
(scoped to Next.js/frontend conventions -- read those when working there instead of duplicating
frontend rules here).

## Commands

```bash
uv sync              # install/refresh the Python workspace (one venv, all packages)
make dev              # FastAPI on :8000 with --reload
make test             # pytest, unit/ + integration/, no live Postgres required
make lint              # ruff check
make format            # ruff format
make docker-up         # Postgres/PostGIS; migrations auto-apply on first boot
make migrate            # re-apply db/migrations/*.sql against a running container
make ingest PDF=data/raw/HAR16-Sirsa-30-06-2011.pdf DISTRICT=Sirsa STATE=Haryana
make trigger-demo      # leave-one-season-out verification of the dry-spell model ladder
```

`make trigger-demo` runs on **synthetic** weather -- it verifies the pipeline is wired and
fast, not that the forecast has skill. Real verification needs IMD gridded rainfall and ECMWF
reforecasts; see `docs/ml-pipeline.md`.

Frontend (`apps/app/`): `pnpm install`, `pnpm dev`, `pnpm test`, `pnpm lint` -- see
`apps/app/AGENTS.md`.

## Conventions that apply everywhere in the Python workspace

- **Thin routes, fat services.** `apps/api` route handlers only translate domain exceptions to
  HTTP status codes; business logic lives in `ankur_domain.services`. See `docs/api.md`
  "Adding an endpoint" for the exact sequence.
- **New repository methods go through the `Protocol` first**, then get implemented in *both*
  `ankur_domain/memory.py` (tests) and `apps/api/app/db.py` (Postgres). The two must stay
  structurally identical -- this is what lets the test suite run without a database.
- **Never widen an invariant to unblock a feature.** If `can_approve()` or
  `initial_review_status()` seem to be in your way, that's a signal to re-read
  `docs/domain-model.md`, not to loosen the check.
- **Nullable over guessed**, always, in anything touching `DACPRuleFields`. See
  `docs/document-intelligence.md` for how the extractor already enforces this (missing/`-`
  cells -> `None`, never inferred).

## Project-local Claude Code skills & subagents

`.claude/skills/` and `.claude/agents/` hold Ankur-specific guidance for coding agents working in
this repo. They're versioned with the repo so any agent session opened here picks them up
automatically. Read the relevant `SKILL.md` before starting work in that area, and prefer
dispatching the matching subagent for scoped, single-area tasks:

| Area | Skill | Subagent |
|---|---|---|
| `services/document-intelligence/` | `dacp-extraction` | `dacp-extraction-engineer` |
| Approval/citation/review-status logic (`ankur_domain.policies`, review routes) | `dacp-domain-invariants` | `domain-invariant-reviewer` (read-only) |
| `apps/api/` | `fastapi-backend` | `backend-api-developer` |
| `apps/app/` | `nextjs-frontend` (+ `apps/app/AGENTS.md`) | `frontend-developer` |
| `docker-compose.yml`, `db/migrations/`, `Makefile`, deploy/env config | `hackathon-deployment` | `deployment-engineer` |

`domain-invariant-reviewer` is read-only by design -- dispatch it to check a change against the
two core invariants before merging, not to implement one.

## Testing philosophy

`tests/unit/` exercises `ankur_domain.policies` and `document_intelligence` scoring/mapping
directly, no I/O. `tests/integration/` runs the real pipeline against the real committed Sirsa
PDF (`data/raw/HAR16-Sirsa-30-06-2011.pdf`) and the FastAPI app with in-memory repositories via
`app.dependency_overrides` -- no live Postgres needed for `make test`. Do not add a live-DB
requirement to the default test run; if you need to test the Postgres-backed repositories
specifically, that's a separate, explicitly-opt-in suite (none exists yet -- see
`docs/database.md` before adding one).
