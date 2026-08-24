# Build context is the repo root (uv workspace: packages/, services/, apps/api,
# pyproject.toml, uv.lock all live at/under repo root and are editable-installed
# together -- see pyproject.toml [tool.uv.workspace]).
#
#   docker build -f apps/api/Dockerfile -t meghmitra-api .

FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/schemas packages/schemas
COPY packages/domain packages/domain
COPY services/document-intelligence services/document-intelligence
COPY services/trigger-engine services/trigger-engine
COPY apps/api apps/api

# --no-dev: prod image doesn't need pytest/ruff. --frozen: fail instead of
# silently re-resolving if uv.lock drifts from pyproject.toml.
RUN uv sync --frozen --no-dev

FROM python:3.12-slim

# poppler-utils: pdftotext, the primary DACP PDF text extractor (see
# docs/document-intelligence.md -- pypdf is the fallback, not the default).
# postgresql-client: psql, used by docker/migrate.sh (run as a k8s
# initContainer against this same image).
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app /app
# db/migrations: read by docker/migrate.sh. data/raw: source DACP PDFs the
# /documents/ingest endpoint reads by repo-relative path (see README "Running
# document ingestion") -- small (~350K), safe to bake into the image.
COPY db/migrations db/migrations
COPY data/raw data/raw

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000"]
