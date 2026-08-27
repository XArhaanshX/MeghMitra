"""Ingest every DACP PDF under `data/raw/` into Postgres, through the exact same
domain-service code path as `POST /documents/ingest` (`app.ingestion.IngestionService`),
just called directly instead of over HTTP. Every extracted rule lands as
`review_status = needs_review` -- this script never approves anything (see
`ankur_domain.policies.can_approve`); that stays a human, via the review API.

State/district resolution for each PDF is identical to `scripts/ingest_all_dacp.py`
(same `iter_targets`, imported from it) so this can't drift from the JSON-only
ingestion path.

Idempotent per PDF: `documents.sha256` has a UNIQUE constraint, so re-running against
a DB that already has a given PDF's document row is a per-file skip (logged), not a
crash or a duplicate.

Usage:
    DATABASE_URL=postgresql://ankur:ankur@localhost:5432/ankur \\
        uv run python scripts/ingest_all_dacp_to_db.py [--raw data/raw]

    # against the hosted DB, after
    # `kubectl -n meghmitra port-forward svc/meghmitra-postgres 5433:5432`:
    DATABASE_URL=postgresql://ankur:<password>@localhost:5433/ankur \\
        uv run python scripts/ingest_all_dacp_to_db.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import traceback
from pathlib import Path

from ankur_domain.services import DocumentService, RuleService

sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402
from app.db import (  # noqa: E402
    PostgresDocumentRepository,
    PostgresExtractionRunRepository,
    PostgresRuleRepository,
    create_pool,
)
from app.ingestion import IngestionService  # noqa: E402
from ingest_all_dacp import iter_targets  # noqa: E402 -- needs sys.path tweak above


async def main_async() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    targets = iter_targets(args.raw)
    print(f"Ingesting {len(targets)} PDF(s) from {args.raw} into {dsn.split('@')[-1]}")

    pool = await create_pool(dsn)
    ingestion = IngestionService(
        documents=DocumentService(documents=PostgresDocumentRepository(pool)),
        rules=RuleService(rules=PostgresRuleRepository(pool)),
        runs=PostgresExtractionRunRepository(pool),
    )

    ok = skipped = errors = 0
    total_rules = total_review = 0
    t0 = time.time()
    for i, (pdf_path, state, district) in enumerate(targets, 1):
        try:
            _, rules, run = await ingestion.ingest_pdf(pdf_path, district=district, state=state)
            ok += 1
            total_rules += run.rules_extracted
            total_review += run.rules_needing_review
        except asyncpg.UniqueViolationError:
            skipped += 1
        except Exception:  # noqa: BLE001 -- log and keep going across hundreds of PDFs
            errors += 1
            print(f"ERROR {pdf_path}: {traceback.format_exc(limit=2)}")
        if i % 50 == 0:
            print(f"{i}/{len(targets)} in {time.time() - t0:.1f}s")

    await pool.close()
    print(
        f"Done: ok={ok} skipped={skipped} errors={errors} total_rules={total_rules} "
        f"needs_review={total_review} elapsed={time.time() - t0:.1f}s"
    )
    return 1 if errors else 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
