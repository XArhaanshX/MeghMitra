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
# postgres container. Safe to re-run only on a fresh database -- migrations
# are not yet idempotent (bootstrap has a single 0001_init.sql).
migrate:
	@for f in db/migrations/*.sql; do \
		echo "applying $$f"; \
		docker compose exec -T db psql -U $${POSTGRES_USER:-ankur} -d $${POSTGRES_DB:-ankur} < $$f; \
	done

# make ingest PDF=data/raw/HAR16-Sirsa-30-06-2011.pdf
ingest:
	@if [ -z "$(PDF)" ]; then echo "usage: make ingest PDF=path/to/document.pdf [DISTRICT=Sirsa] [STATE=Haryana]"; exit 1; fi
	uv run python -m document_intelligence.ingest $(PDF) --district "$(DISTRICT)" --state "$(STATE)"

docker-up:
	docker compose up -d

docker-down:
	docker compose down
