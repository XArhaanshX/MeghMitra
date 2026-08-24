.PHONY: dev test lint format migrate ingest docker-up docker-down sync

DISTRICT ?= Sirsa
STATE ?= Haryana
PDF ?=

sync:
	uv sync

dev:
	uv run uvicorn app.main:app --reload --app-dir apps/api --host 0.0.0.0 --port 8000

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

# Applies db/migrations/*.sql, in order, against the running docker-compose
# postgres container. Idempotent: each migration file registers itself in
# schema_migrations (see the footer of 0001_init.sql), so already-applied
# migrations (including 0001_init.sql, auto-run by docker-entrypoint-initdb.d
# on first container boot) are skipped instead of re-erroring on "already
# exists". -v ON_ERROR_STOP=1 makes a genuine SQL error fail the target.
PSQL := docker compose exec -T db psql -v ON_ERROR_STOP=1 -U $${POSTGRES_USER:-ankur} -d $${POSTGRES_DB:-ankur}

migrate:
	@$(PSQL) -c "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());" > /dev/null
	@for f in db/migrations/*.sql; do \
		name=$$(basename $$f); \
		applied=$$($(PSQL) -tAc "SELECT 1 FROM schema_migrations WHERE filename = '$$name'"); \
		if [ "$$applied" = "1" ]; then \
			echo "skip $$f (already applied)"; \
		else \
			echo "applying $$f"; \
			$(PSQL) < $$f; \
		fi; \
	done

# make ingest PDF=data/raw/HAR16-Sirsa-30-06-2011.pdf
ingest:
	@if [ -z "$(PDF)" ]; then echo "usage: make ingest PDF=path/to/document.pdf [DISTRICT=Sirsa] [STATE=Haryana]"; exit 1; fi
	uv run python -m document_intelligence.ingest $(PDF) --district "$(DISTRICT)" --state "$(STATE)"

docker-up:
	docker compose up -d

docker-down:
	docker compose down
