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
COPY packages/geo packages/geo
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
# db/migrations: read by docker/migrate.sh (small, needed at image-build time
# to construct the image but really applied by the initContainer/entrypoint
# against Postgres, not read from disk by the API process itself).
# data/fixtures: the hand-curated demo seed drafts `app.seed` reads via
# `_repo_root()` (tiny, ~12KB total) -- needed so `make seed` /
# `make seed-multi-state` can run against this image.
#
# The DACP corpus itself (data/raw source PDFs, data/processed extracted
# rules) is NOT baked into this image -- it's ~317MB across 647 PDFs, versus
# the handful of KB db/migrations and data/fixtures need. Mount it as a
# named volume or bind mount at container start instead (see
# docker-compose.yml's api service for an example), and point
# ANKUR_RAW_ROOT / ANKUR_CORPUS_ROOT (below, see apps/api/app/config.py) at
# the mount if it isn't at the default `/app/data/raw` /
# `/app/data/processed`. Without a mount, document ingestion and coverage
# endpoints that read the corpus will find nothing there.
COPY db/migrations db/migrations
COPY data/fixtures data/fixtures

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ANKUR_RAW_ROOT=data/raw \
    ANKUR_CORPUS_ROOT=data/processed

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000"]
