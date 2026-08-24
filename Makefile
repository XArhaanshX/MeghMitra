.PHONY: help dev web test lint format migrate ingest seed trigger-demo docker-up docker-down docker-reset logs ps psql sync
.DEFAULT_GOAL := help

DISTRICT ?= Sirsa
STATE ?= Haryana
PDF ?=
SERVICE ?=

help: ## Show this list of targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

sync: ## Install/refresh the Python workspace (one venv, all packages)
	uv sync

dev: docker-up migrate ## Start Postgres (if needed), apply pending migrations, then run FastAPI with --reload on :8000
	uv run uvicorn app.main:app --reload --app-dir apps/api --host 0.0.0.0 --port 8000

web: ## Run the Next.js dashboard dev server on :3000 (run `make dev` in another terminal first)
	cd apps/app && pnpm dev

test: ## Run the pytest suite (unit/ + integration/, no live Postgres required)
	uv run pytest

lint: ## Run ruff check
	uv run ruff check .

format: ## Run ruff format
	uv run ruff format .

# Applies db/migrations/*.sql against the running docker-compose postgres
# container. Idempotent (see scripts/migrate.py). Shared with Windows:
# `.\scripts\dev.ps1 migrate`.
migrate: docker-up ## Apply db/migrations/*.sql against a running container (idempotent)
	uv run python scripts/migrate.py

# make ingest PDF=data/raw/HAR16-Sirsa-30-06-2011.pdf
ingest: ## Run document ingestion: make ingest PDF=path.pdf [DISTRICT=Sirsa] [STATE=Haryana]
	@if [ -z "$(PDF)" ]; then echo "usage: make ingest PDF=path/to/document.pdf [DISTRICT=Sirsa] [STATE=Haryana]"; exit 1; fi
	uv run python -m document_intelligence.ingest $(PDF) --district "$(DISTRICT)" --state "$(STATE)"

seed: docker-up migrate ## Load 3 cited Sirsa demo rules (validate_draft, then ReviewService.approve)
	uv run python -m app.seed

# Runs on SYNTHETIC weather -- verifies the pipeline is wired and fast, not that
# the forecast has skill. Real verification needs IMD gridded rainfall and ECMWF
# reforecasts; see docs/ml-pipeline.md.
trigger-demo: ## Leave-one-season-out verification of the dry-spell model ladder (synthetic weather)
	uv run python -m trigger_engine

docker-up: ## Start Postgres/PostGIS via docker-compose and wait until it's healthy (migrations auto-apply on first boot)
	docker compose up -d --wait

docker-down: ## Stop and remove the docker-compose containers (add -v manually to drop the volume)
	docker compose down

docker-reset: ## Stop containers, drop the volume, and start fresh (schema re-applies from scratch)
	docker compose down -v
	$(MAKE) docker-up

logs: ## Follow docker-compose logs (all services; pass SERVICE=db to scope)
	docker compose logs -f $(SERVICE)

ps: ## Show docker-compose container status
	docker compose ps

psql: ## Open an interactive psql shell into the running Postgres container
	docker compose exec db psql -U $${POSTGRES_USER:-ankur} -d $${POSTGRES_DB:-ankur}

# Windows (no GNU make): .\scripts\dev.ps1 <target>  e.g. docker-up, migrate, seed, dev
