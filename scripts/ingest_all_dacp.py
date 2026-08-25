"""Ingest every DACP PDF under `data/raw/` into
`data/processed/<state-slug>/<district-slug>/<stem>.json`.

Runs `document_intelligence.pipeline.run_ingestion` in-process for every PDF (much faster
than shelling out to `document_intelligence.ingest` once per file) using the district/state
each file was downloaded under (see `scripts/download_dacp.py`).

State/district for each PDF is taken from its path: `data/raw/<State>/<file>.pdf`. This
repo's one hand-placed exception, `data/raw/HAR16-Sirsa-30-06-2011.pdf` (Haryana/Sirsa), is
special-cased since it predates the `<State>/` subdirectory convention.

THE OUTPUT PATH IS DETERMINISTIC, KEYED ON (STATE, DISTRICT, SOURCE FILE)

Earlier versions of this script wrote `<district>/<stem>.json` -- district only,
no state. Two problems followed: (1) two states that happen to share a district
name (Bijapur: Karnataka and Chhattisgarh) wrote into the *same* directory, and
(2) re-running after a `naming.py` fix left the previous run's files behind
under their old directory name, so the corpus accumulated 626 stale duplicate
directories that `RuleStore`/`ankur_geo.districts` could only work around with
an mtime heuristic. The state-qualified, source-filename-keyed path this
version writes is stable across re-runs: re-ingesting the same PDF overwrites
the same file rather than adding a new one under a new name.

STATE NAMES ARE CANONICALIZED

The raw download directories include real misspellings (`Maharastra`,
`Chattisgarh`, `Orissa`, `Uttarkhand`) alongside the correctly-spelled ones.
`ankur_geo.state_by_name_or_alias` resolves both spellings to the same
canonical `State`; this script stores and slugs the CANONICAL name so
`document.state` in the persisted JSON -- and the directory it lives under --
agree with what `ankur_geo`, the API and the frontend all use as ground
truth. A raw directory name `ankur_geo` cannot resolve is kept as-is (this
should not happen; all 30 raw directories are covered by the 36 canonical
names or the 7 known aliases) and is loudly logged, never silently guessed.

Usage:
    uv run python scripts/ingest_all_dacp.py [--raw data/raw] [--out data/processed]
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

from ankur_geo import district_key, state_by_name_or_alias
from document_intelligence.naming import district_from_filename
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
            raw_state = rel.parts[0].replace("_", " ")
            matched = state_by_name_or_alias(raw_state)
            if matched is None:
                print(f"WARNING: unrecognized state directory {rel.parts[0]!r}; keeping as-is")
            state = matched.name if matched is not None else raw_state
            # The stem is `<state-code><serial>-<district>-<date>`; recording it
            # verbatim gave the corpus districts named "NL2-Wokha-20.11.2014",
            # which nothing downstream can look up. See `naming.py`.
            district = district_from_filename(pdf_path.stem, state=state)
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
        state_slug = state.lower().replace(" ", "_")
        district_slug = district_key(district) or "unknown"
        out_path = args.out / state_slug / district_slug / f"{pdf_path.stem}.json"
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
