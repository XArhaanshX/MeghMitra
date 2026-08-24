# API reference

FastAPI app: `apps/api/app/main.py`. Routes are intentionally thin -- every handler delegates to
an `ankur_domain` service (`apps/api/app/deps.py` wires `Request` -> repository -> service via
`app.dependency_overrides`-friendly factory functions). Business logic lives in
`ankur_domain.services` and `ankur_domain.policies`, never in a route handler.

| Method | Path | Service call | Notes |
|---|---|---|---|
| GET | `/health` | -- | No DB dependency; always 200 once the process is up. |
| GET | `/documents` | `DocumentService.list` | |
| GET | `/documents/{id}` | `DocumentService.get` | 404 via `DocumentNotFoundError`. |
| POST | `/documents/ingest` | `IngestionService.ingest_pdf` | Body: `{path, district, state}`. `path` is a server-local filesystem path (no file upload in this bootstrap). Runs the full `document_intelligence` pipeline synchronously and persists document + rules + run. |
| GET | `/rules` | `RuleService.list` | Optional `?review_status=` query filter. |
| GET | `/rules/{id}` | `RuleService.get` | 404 via `RuleNotFoundError`. |
| GET | `/rules/{id}/citation` | `RuleService.citation_for` | Answers "why did Ankur produce this recommendation?". |
| GET | `/review-queue` | `ReviewService.review_queue` | Rules with `review_status = needs_review`. |
| POST | `/rules/{id}/approve` | `ReviewService.approve` | Body: `{reviewed_by}`. 422 via `RuleNotApprovableError` if the rule has no valid citation -- this is the core invariant enforced at the HTTP boundary. |
| POST | `/rules/{id}/reject` | `ReviewService.reject` | Body: `{reviewed_by, reason?}`. |

## Adding an endpoint

1. Add/extend a method on the relevant `ankur_domain.services` class first (with a unit test in
   `tests/unit/`, no HTTP involved).
2. Add a thin route in `apps/api/app/routes/*.py` that calls it and translates domain exceptions
   to HTTP status codes (see the `try/except RuleNotFoundError -> HTTPException(404)` pattern
   already used everywhere).
3. If it needs a new repository method, add it to the `Protocol` in
   `ankur_domain/repositories.py` first, then implement it in *both*
   `ankur_domain/memory.py` (in-memory, used by tests) and `apps/api/app/db.py`
   (Postgres) -- the two must stay structurally identical.
4. Add an integration test in `tests/integration/test_rules_api.py` using the existing
   `client`/`rule_repo` fixtures (in-memory, no live Postgres needed).

## Dependency injection pattern

`app.state.pool` (an `asyncpg.Pool`, created in `main.py`'s `lifespan`) is the only global
mutable state. Everything else is request-scoped via `Depends(get_*_service)`. Tests never touch
`app.state.pool` directly -- they override the `get_*_service` dependency functions with
factories that close over in-memory repositories (see `tests/integration/test_rules_api.py`).
If `DATABASE_URL` is unreachable at startup, `app.state.pool` stays `None` and DB-backed routes
return `503` rather than crashing the whole process (`/health` still returns `200`).
