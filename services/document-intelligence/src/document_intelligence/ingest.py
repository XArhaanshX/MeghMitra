"""CLI entry point: `python -m document_intelligence.ingest path/to/document.pdf`.

Runs the ingestion pipeline and writes a JSON result (document metadata +
extracted rules) next to `--out`, defaulting under `data/processed/`.
Prints a short summary, including the review-queue count, to stdout.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from document_intelligence.pipeline import run_ingestion

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("document_intelligence.ingest")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m document_intelligence.ingest",
        description="Ingest a DACP PDF and extract structured, cited rule drafts.",
    )
    parser.add_argument("pdf", type=Path, help="Path to the DACP PDF to ingest.")
    parser.add_argument(
        "--district", required=True, help="District the plan applies to, e.g. Sirsa."
    )
    parser.add_argument("--state", required=True, help="State the plan applies to, e.g. Haryana.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to data/processed/<district>/<pdf-stem>.json.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.pdf.exists():
        logger.error("PDF not found: %s", args.pdf)
        return 1

    out_path = args.out or Path("data/processed") / args.district.lower() / f"{args.pdf.stem}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Ingesting %s (district=%s, state=%s)", args.pdf, args.district, args.state)
    result = run_ingestion(args.pdf, district=args.district, state=args.state)

    payload = {
        "document": json.loads(result.document.model_dump_json()),
        "run": json.loads(result.run.model_dump_json()),
        "rules": [json.loads(rule.model_dump_json()) for rule in result.rules],
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    needs_review = result.run.rules_needing_review
    logger.info(
        "Extracted %d rule(s) from %d page(s); %d flagged needs_review. Wrote %s",
        result.run.rules_extracted,
        result.run.pages_processed,
        needs_review,
        out_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
