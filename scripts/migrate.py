"""Apply `db/migrations/*.sql` against the docker-compose Postgres, in order.

Idempotent: each file registers itself in `schema_migrations` (see the footer of
`0001_init.sql`). Already-applied files are skipped, including `0001_init.sql`
which docker-entrypoint-initdb.d runs on first container boot.

Uses `psql` inside the `db` container so a whole file (multiple statements)
applies correctly -- asyncpg cannot run multi-statement scripts. The migration
files are already mounted at `/docker-entrypoint-initdb.d`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "db" / "migrations"
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.sql$")


def _psql(*args: str) -> subprocess.CompletedProcess[str]:
    user = os.environ.get("POSTGRES_USER", "ankur")
    db = os.environ.get("POSTGRES_DB", "ankur")
    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "db",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        user,
        "-d",
        db,
        *args,
    ]
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)


def main() -> None:
    _psql(
        "-c",
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());",
    )
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if not SAFE_FILENAME.match(path.name):
            raise SystemExit(f"refusing to apply oddly named migration: {path.name}")
        applied = _psql(
            "-tAc",
            f"SELECT 1 FROM schema_migrations WHERE filename = '{path.name}'",
        )
        rel = path.relative_to(ROOT).as_posix()
        if applied.stdout.strip() == "1":
            print(f"skip {rel} (already applied)")
            continue
        print(f"applying {rel}")
        _psql("-f", f"/docker-entrypoint-initdb.d/{path.name}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        if err:
            print(err, file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
