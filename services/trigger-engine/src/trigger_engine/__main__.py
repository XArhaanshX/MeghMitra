"""CLI entry point: `uv run python -m trigger_engine` (or `make trigger-demo`).

Mirrors `document_intelligence.ingest`, the workspace's other runnable, so both
services are driven the same way.

Runs the full leave-one-season-out sweep on synthetic weather and prints the
verification table. The banner about synthetic data goes to stderr rather than
stdout, so piping the table somewhere does not quietly strip the one caveat that
makes the numbers honest.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from trigger_engine.pipeline import format_report, run_demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trigger_engine",
        description="Leave-one-monsoon-season-out verification of the dry-spell model ladder.",
    )
    parser.add_argument(
        "--start-season", type=int, default=1995, help="First monsoon season (default: 1995)."
    )
    parser.add_argument(
        "--end-season", type=int, default=2025, help="Last monsoon season, inclusive."
    )
    parser.add_argument(
        "--lead-days",
        type=int,
        default=14,
        help="Forecast horizon in days: does a dry spell begin within (t, t+L]?",
    )
    parser.add_argument("--verbose", action="store_true", help="Show pipeline stage logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    print(
        "NOTE: weather is SYNTHETIC (trigger_engine.synthetic). These numbers show the\n"
        "      pipeline is wired correctly and runs fast. They say nothing about real\n"
        "      forecast skill -- that needs IMD gridded rainfall and ECMWF reforecasts.\n"
        "      See docs/ml-pipeline.md.\n",
        file=sys.stderr,
    )

    started = time.perf_counter()
    artifacts = run_demo(
        seasons=range(args.start_season, args.end_season + 1), lead_days=args.lead_days
    )
    print(format_report(artifacts))
    print(f"\ntotal wall time: {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
