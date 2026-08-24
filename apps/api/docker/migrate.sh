#!/usr/bin/env sh
# Applies db/migrations/*.sql against $DATABASE_URL, idempotently -- the k8s
# equivalent of `make migrate`. Run as an initContainer (using this same api
# image) ahead of every apps/api rollout; safe to re-run, already-applied
# migrations are skipped via the schema_migrations table each migration file
# registers itself into (see db/migrations/0001_init.sql footer).
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());" \
  > /dev/null

for f in db/migrations/*.sql; do
  name=$(basename "$f")
  applied=$(psql "$DATABASE_URL" -tAc "SELECT 1 FROM schema_migrations WHERE filename = '$name'")
  if [ "$applied" = "1" ]; then
    echo "skip $f (already applied)"
  else
    echo "applying $f"
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
  fi
done
