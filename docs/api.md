# API reference

FastAPI app: `apps/api/app/main.py`. Routes are intentionally thin -- every handler delegates to
an `ankur_domain` service (`apps/api/app/deps.py` wires `Request` -> repository -> service via
`app.dependency_overrides`-friendly factory functions). Business logic lives in
`ankur_domain.services` and `ankur_domain.policies`, never in a route handler.

| Method | Path | Service call | Notes |
|---|---|---|---|
| GET | `/health` | -- | No DB dependency; always 200 once the process is up. |
| GET | `/documents` | `DocumentService.list` | Optional `?state=`, `?limit=` (max 200), `?offset=`. |
| GET | `/documents/{id}` | `DocumentService.get` | 404 via `DocumentNotFoundError`. |
| GET | `/documents/{id}/pages` | `DocumentService.list_pages` | Page text for the citation viewer. 404 if the document is missing. |
| GET | `/documents/{id}/pages/{n}` | `DocumentService.get_page` | One 1-indexed page. 404 if the page was never stored. |
| POST | `/documents/ingest` | `IngestionService.ingest_pdf` | Body: `{path, district, state}`. `path` is a server-local filesystem path (no file upload in this bootstrap). Runs the full `document_intelligence` pipeline synchronously and persists document + **pages** + rules + run. |
| GET | `/rules` | `RuleService.list` / `list_advisory_eligible` | Optional `?review_status=`, `?district=`, `?state=`, `?advisory_eligible=true` (approved + cited only), `?limit=`, `?offset=`. |
| GET | `/rules/{id}` | `RuleService.get` | 404 via `RuleNotFoundError`. Single-item shape, unaffected by pagination. |
| GET | `/rules/{id}/citation` | `RuleService.citation_for` | Answers "why did Ankur produce this recommendation?". |
| GET | `/review-queue` | `ReviewService.review_queue` | Rules with `review_status = needs_review`. Optional `?state=`, `?limit=`, `?offset=`. |
| POST | `/rules/{id}/approve` | `ReviewService.approve` | Body: `{reviewed_by}`. 422 via `RuleNotApprovableError` if the rule has no valid citation -- this is the core invariant enforced at the HTTP boundary. |
| POST | `/rules/{id}/reject` | `ReviewService.reject` | Body: `{reviewed_by, reason?}`. |
| POST | `/advisories` | `AdvisoryEmissionService.evaluate` | Body: `{district, state?, moisture, forecast, cost_loss_ratio?, crop_already_sown?}`. `state` is resolved (never guessed) via `apps/api/app/routes/advisories.py`'s `_resolve_state` -- see "State resolution" below. Detects a `condition_code` from the moisture state, joins **only** approved+cited rules for that `(state, district)`, then cost-loss. Default action is `abstain`. Always writes a `trigger_events` row (including silence); writes `advisories` only when something was actually said. 201. |
| GET | `/advisories` | `AdvisoryEmissionService.list_advisories` | Non-silent emissions only. Optional `?state=`, `?limit=`, `?offset=`. |
| GET | `/trigger-events` | `AdvisoryEmissionService.list_events` | Full evaluation audit log, including ABSTAIN. Optional `?state=`, `?limit=`, `?offset=`. |
| GET | `/geo/states` | -- (`ankur_geo.STATES` + `DocumentService.list`) | All 36 states/UTs: `{state_code, name, slug, kind, has_dacp_coverage, document_count, district_count}`. `has_dacp_coverage`/`district_count` come from the corpus-derived `ankur_geo.DISTRICTS` snapshot; `document_count` is a live count from the document repository. Read-only, no pagination (36 rows). |
| GET | `/geo/states/{state_code}/districts` | -- (`ankur_geo.DISTRICTS`) | Districts ingested for one state: `{district_code, name, slug}`. 404 for an unrecognized `state_code`. |
| GET | `/coverage` | -- (`DocumentService.list` + `RuleService.list`) | `{documents, rules, approved_rules, unmapped_rules, districts, district_name_collisions, by_code, by_review_status}` -- national corpus health, mirrors `trigger_engine.rulestore.RuleStore.coverage()`'s semantics but reads the live document/rule repositories instead of rescanning `data/processed/`. |

## Pagination envelope

`GET /documents`, `/rules`, `/review-queue`, `/advisories`, `/trigger-events` accept optional
`limit` (1-200) and `offset` (>=0) query params, applied via `apps/api/app/deps.py`'s
`paginated()` helper. Passing **neither** returns the bare `list[...]` these endpoints always
returned -- existing clients see no change. Passing **either** switches the response to
`{"items": [...], "total": int, "limit": int, "offset": int}`, where `total` is a second,
unbounded fetch under the same filters (there is no separate `COUNT` query in any repository
`Protocol`). `GET /rules/{id}` and the other single-item endpoints are unaffected.

## State resolution

District names are not globally unique in the national corpus (Bijapur: Karnataka and
Chhattisgarh; six more, see `docs/decisions.md`). Every endpoint that filters or evaluates
against a `district` also accepts an optional `state`:

- **List endpoints** (`/rules?state=`, `/documents?state=`, etc.) filter by state as a plain
  column match (`state_code ILIKE`) -- omitting it returns the national result, never a guess.
- **`POST /advisories`** must resolve exactly one state before it can look up rules, so an
  ambiguous `district` with no `state` is a **422**, not a guess: `_resolve_state()` calls
  `ankur_geo.states_with_district_name(district)`, auto-resolves when unambiguous, and requires
  `state` when it is not. A `state` that does not match the given `district` in the corpus is
  also a 422, via `ankur_geo.resolve_region()`'s `RegionResolutionError`, with a message naming
  the correct state(s).

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
   never inserted as `approved`. `make seed-multi-state` additionally seeds two more real,
   cited plans (Dimapur, Nagaland and Mpur Imphal East, Manipur) the same way, for exercising
   the state-aware endpoints beyond Sirsa.
2. `GET /rules?advisory_eligible=true&district=Sirsa&state=Haryana` — the joinable set for the
   trigger. `state` is optional here (list endpoints filter, never require it), but pinning it
   avoids ambiguity for a district name that happens to collide across states.
3. `POST /advisories` with a dry-spell-after-sowing moisture state (example on the
   `EvaluateRequest` schema in `/docs`) — expect `re_sow` + Pearl millet HHB-67 + page 9.
4. `GET /rules/{id}/citation` — “why did Ankur say this?”
5. `GET /geo/states` / `GET /coverage` — national reference data and corpus health, independent
   of any one district's demo data.

`POST /rules/{id}/approve` returns **422** if the citation page is past the source
document's `page_count` (the Sirsa PDF has 31 pages), or if `source_text` is set
and does not appear on the stored page.

CORS origins come from `CORS_ORIGINS` (comma-separated) in `.env`. Default is
`http://localhost:3000,http://127.0.0.1:3000`.

### Example `POST /advisories` body

```json
{
  "state": "Haryana",
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

`state` is optional on this body -- it is only *required* when `district` is ingested for more
than one state (see "State resolution" above). A `Bijapur` request without `state` is a 422
naming Karnataka and Chhattisgarh.

