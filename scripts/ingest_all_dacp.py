"""Ingest every DACP PDF under `data/raw/` into `data/processed/<district>/<stem>.json`.

Runs `document_intelligence.pipeline.run_ingestion` in-process for every PDF (much faster
than shelling out to `document_intelligence.ingest` once per file) using the district/state
each file was downloaded under (see `scripts/download_dacp.py`).

State/district for each PDF is taken from its path: `data/raw/<State>/<file>.pdf`. This
repo's one hand-placed exception, `data/raw/HAR16-Sirsa-30-06-2011.pdf` (Haryana/Sirsa), is
special-cased since it predates the `<State>/` subdirectory convention.

Usage:
    uv run python scripts/ingest_all_dacp.py [--raw data/raw] [--out data/processed]
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

from document_intelligence.pipeline import run_ingestion

_SPECIAL_CASE = {
    "HAR16-Sirsa-30-06-2011.pdf": ("Haryana", "Sirsa"),
}


def iter_targets(raw_root: Path) -> list[tuple[Path, str, str]]:
    targets: list[tuple[Path, str, str]] = []
    for pdf_path in sorted(raw_root.rglob("*.pdf")):
        rel = pdf_path.relative_to(raw_root)
        if pdf_path.name in _SPECIAL_CASE:
            state, district = _SPECIAL_CASE[pdf_path.name]
        elif len(rel.parts) >= 2:
            state = rel.parts[0].replace("_", " ")
            district = pdf_path.stem
        else:
            continue
        targets.append((pdf_path, state, district))
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, default=Path("data/processed"))
    args = parser.parse_args()

    targets = iter_targets(args.raw)
    print(f"Ingesting {len(targets)} PDF(s) from {args.raw}")

    ok = errors = 0
    total_rules = total_review = 0
    t0 = time.time()
    for i, (pdf_path, state, district) in enumerate(targets, 1):
        out_path = args.out / district.lower().replace(" ", "_") / f"{pdf_path.stem}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = run_ingestion(pdf_path, district=district, state=state)
            payload = {
                "document": json.loads(result.document.model_dump_json()),
                "run": json.loads(result.run.model_dump_json()),
                "rules": [json.loads(rule.model_dump_json()) for rule in result.rules],
            }
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            ok += 1
            total_rules += result.run.rules_extracted
            total_review += result.run.rules_needing_review
        except Exception:  # noqa: BLE001 -- log and keep going across hundreds of PDFs
            errors += 1
            print(f"ERROR {pdf_path}: {traceback.format_exc(limit=2)}")
        if i % 50 == 0:
            print(f"{i}/{len(targets)} in {time.time() - t0:.1f}s")

    print(
        f"Done: ok={ok} errors={errors} total_rules={total_rules} "
        f"needs_review={total_review} elapsed={time.time() - t0:.1f}s"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
