---
name: hackathon-deployment
description: Preparing Ankur for a demo/deployment -- environment config, running the full stack together, a deploy checklist, or deciding what infra a new feature needs. Use to keep infra decisions appropriately small for a SIH hackathon prototype.
---

# Deployment (hackathon scope)

There is no CI/CD or hosting configured yet -- this skill is the checklist for standing the
stack up for a demo, and the guardrails for what NOT to add while doing it.

## Stack, as-is

```text
Postgres/PostGIS  <- docker-compose.yml (db/migrations/*.sql auto-applied on first boot)
apps/api          <- FastAPI, uvicorn, connects via DATABASE_URL
apps/app          <- Next.js, calls apps/api via NEXT_PUBLIC_API_URL
```

Three processes, one Postgres instance, no message queue, no cache, no separate worker process.
`POST /documents/ingest` runs the extraction pipeline inline in the HTTP request -- there is no
background job system to deploy.

## Running the full stack locally (demo dry run)

```bash
cp .env.example .env                 # backend: DATABASE_URL, POSTGRES_*, API_HOST/PORT
cp apps/app/example.env apps/app/.env.local   # frontend: NEXT_PUBLIC_API_URL
make dev                             # brings up Postgres (waits for healthy), applies migrations, runs FastAPI on :8000
# separate terminal:
make web                             # or: cd apps/app && pnpm install && pnpm dev -- Next.js on :3000
```

`make dev` depends on `docker-up` (`docker compose up -d --wait`, so it blocks until Postgres's
healthcheck passes -- no race between "Postgres is starting" and "API tries to connect") and
`migrate` (idempotent). Useful during a demo: `make logs SERVICE=db`, `make psql`, `make ps`,
`make docker-reset` (wipe and restart Postgres from scratch).

Verify before a demo: `curl localhost:8000/health` returns `{"status":"ok"}`, then run
`make ingest PDF=data/raw/HAR16-Sirsa-30-06-2011.pdf` (or `POST /documents/ingest`) and confirm
`GET /rules` returns data.

## Deploying (single host / VM is enough)

This project has no Kubernetes manifests and should not gain any for the hackathon. A single VM
or container host running `docker compose` (Postgres) plus two processes (`uvicorn`, `next
start` or a static export) is sufficient scale for a SIH demo. If asked to "deploy this":

1. Provision Postgres (the same `docker-compose.yml` service works standalone on a VM, or use a
   managed Postgres if one's already available -- either way, run `make migrate` against it
   once reachable).
2. Set real values for `.env` (`DATABASE_URL` pointing at the deployed Postgres, `API_HOST=0.0.0.0`)
   and `apps/app/.env.local` (`NEXT_PUBLIC_API_URL` pointing at the deployed API's public URL).
3. Run `uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port 8000` behind whatever
   reverse proxy/TLS termination the host provides (nginx, Caddy, or the platform's built-in
   one) -- do not add a reverse proxy config to this repo speculatively; only add one if a
   specific host requires it.
4. `pnpm build && pnpm start` (or the platform's Next.js build step) for `apps/app`.
5. `GET /health` is the readiness check -- it never touches the database, so it reports process
   liveness even if Postgres isn't reachable yet (DB-backed routes return `503` until it is).

## Guardrails (from the original project brief -- do not reintroduce these)

Do not add, even "just for deployment": Kubernetes, Kafka, Redis (unless a specific feature
demonstrably needs a queue/cache -- none does yet), a vector database, microservices split
beyond the existing `apps/`/`services/` boundary, or CI pipelines more elaborate than "run
`make lint && make test`". If a deployment target imposes one of these (e.g. a PaaS that only
speaks containers), satisfy it with the minimum required wrapper (a `Dockerfile` per app) rather
than restructuring the project around it.
