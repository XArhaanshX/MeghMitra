---
name: fastapi-backend
description: Adding or changing anything in apps/api/ -- new endpoints, request/response models, dependency wiring, or Postgres-backed repositories. Use for backend feature work; use dacp-domain-invariants instead for approval/citation/review-status logic specifically.
---

# FastAPI backend (`apps/api/`)

Full reference: `docs/api.md`. This skill is the fast path for adding backend features without
breaking the thin-route convention -- appropriate depth for a hackathon prototype, not a
generic "how to FastAPI" guide.

## The rule: routes translate, services decide

`apps/api/app/routes/*.py` handlers do exactly two things: call one `ankur_domain` service
method, and translate its exceptions to HTTP status codes (`try/except SomeDomainError:
raise HTTPException(...)`). If you're writing an `if`/business-rule check inside a route
handler, it belongs in `ankur_domain/services.py` instead.

## Adding an endpoint (concrete steps)

1. Add or extend a method on the relevant class in `packages/domain/src/ankur_domain/services.py`
   (`DocumentService`, `RuleService`, `ReviewService`, or a new one). Write its unit test in
   `tests/unit/` first if the logic is non-trivial -- no HTTP involved at this step.
2. If it needs new persistence, add the method to the `Protocol` in
   `ankur_domain/repositories.py` first, then implement it in **both**
   `ankur_domain/memory.py` (in-memory, used by tests) and `apps/api/app/db.py` (Postgres,
   raw `asyncpg` SQL -- no ORM in this project). They must behave identically.
3. Add a thin route in `apps/api/app/routes/*.py`. Reuse the existing
   `Depends(get_*_service)` pattern from `apps/api/app/deps.py`; add a new `get_*_service`
   factory there only if the endpoint needs a service that doesn't exist yet.
4. Add a `pydantic.BaseModel` request/response shape in the route file itself if the domain
   schema (`ankur_schemas`) doesn't already cover it -- don't add API-only fields to
   `ankur_schemas` models.
5. Add an integration test to `tests/integration/test_rules_api.py` (or a new file following its
   pattern) using the existing `client`/`rule_repo` fixtures. No live Postgres needed --
   `app.dependency_overrides` swaps in-memory repositories for the Postgres ones.

## Hackathon-appropriate scope

- No auth/authz layer exists yet. If the demo needs to gate an endpoint, a minimal
  header-based check is enough -- do not reach for OAuth/JWT/session infra for this prototype.
- No pagination on list endpoints (`/rules`, `/documents`) yet. Add `limit`/`offset` query
  params only if the demo dataset actually gets large enough to need it -- don't pre-build it.
- Keep new endpoints synchronous-feeling even though the stack is async: no background job
  queue, no Celery/Redis. `POST /documents/ingest` already runs the full pipeline inline in the
  request -- follow that pattern for anything similarly sized.

## Running just this layer

```bash
uv run pytest tests/integration/test_rules_api.py -q
uv run uvicorn app.main:app --reload --app-dir apps/api   # or: make dev
curl localhost:8000/health
```
