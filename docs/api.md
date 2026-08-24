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
| GET | `/rules` | `RuleService.list` / `list_advisory_eligible` | Optional `?review_status=`, `?district=`, `?advisory_eligible=true` (approved + cited only). |
| GET | `/rules/{id}` | `RuleService.get` | 404 via `RuleNotFoundError`. |
| GET | `/rules/{id}/citation` | `RuleService.citation_for` | Answers "why did Ankur produce this recommendation?". |
| GET | `/review-queue` | `ReviewService.review_queue` | Rules with `review_status = needs_review`. |
| POST | `/rules/{id}/approve` | `ReviewService.approve` | Body: `{reviewed_by}`. 422 via `RuleNotApprovableError` if the rule has no valid citation -- this is the core invariant enforced at the HTTP boundary. |
| POST | `/rules/{id}/reject` | `ReviewService.reject` | Body: `{reviewed_by, reason?}`. |
| POST | `/advisories` | `AdvisoryEmissionService.evaluate` | Body: `{district, moisture, forecast, cost_loss_ratio?, crop_already_sown?}`. Detects a `condition_code` from the moisture state, joins **only** approved+cited rules for that district, then cost-loss. Default action is `abstain`. Always writes a `trigger_events` row (including silence); writes `advisories` only when something was actually said. 201. |
| GET | `/advisories` | `AdvisoryEmissionService.list_advisories` | Non-silent emissions only. |
| GET | `/trigger-events` | `AdvisoryEmissionService.list_events` | Full evaluation audit log, including ABSTAIN. |

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

## Frontend loop (Sirsa demo)

Interactive docs: `http://localhost:8000/docs`.

1. `make docker-up && make migrate && make seed && make dev` — three cited Sirsa rules
   (pages 7, 9, 10 of the 31-page PDF) are validated then **approved via** `ReviewService`,
   never inserted as `approved`.
2. `GET /rules?advisory_eligible=true&district=Sirsa` — the joinable set for the trigger.
3. `POST /advisories` with a dry-spell-after-sowing moisture state (example on the
   `EvaluateRequest` schema in `/docs`) — expect `re_sow` + Pearl millet HHB-67 + page 9.
4. `GET /rules/{id}/citation` — “why did Ankur say this?”

`POST /rules/{id}/approve` returns **422** if the citation page is past the source
document's `page_count` (the Sirsa PDF has 31 pages).

### Example `POST /advisories` body

```json
{
  "district": "Sirsa",
  "crop_already_sown": true,
  "moisture": {
    "block_id": "sirsa-block-1",
    "as_of": "2020-07-15",
    "soil_moisture_fraction": 0.2,
    "consecutive_dry_days": 10,
    "days_since_sowing": 10,
    "onset_delay_days": null,
    "rain_3d_mm": 0,
    "rain_3d_normal_mm": 10
  },
  "forecast": {
    "block_id": "sirsa-block-1",
    "issued_on": "2020-07-15",
    "lead_days": 14,
    "probability": 0.8,
    "climatological_rate": 0.2,
    "model_version": "trigger-engine/0.1.0"
  }
}
```
