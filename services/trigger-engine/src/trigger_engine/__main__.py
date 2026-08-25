"""CLI entry point: `uv run python -m trigger_engine` (or `make trigger-demo`).

Mirrors `document_intelligence.ingest`, the workspace's other runnable, so both
services are driven the same way.

Two modes:

  (no flags)    Leave-one-season-out verification of the model ladder. Prints the
                skill table. This is what `make trigger-demo` runs.

  --district X  The full end-to-end path: load the ingested DACP rule base, run
                the weather through the model, and decide -- for every block-day
                of the evaluation season -- whether an advisory may be emitted.
                Prints what was said, and what was not, and why.

The banner about synthetic data goes to stderr rather than stdout, so piping the
table somewhere does not quietly strip the one caveat that makes the numbers
honest.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

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
    parser.add_argument(
        "--district",
        help="Run the end-to-end path for this district instead of the skill table.",
    )
    parser.add_argument(
        "--state",
        help=(
            "State the --district plan belongs to. Optional when the district name "
            "is unambiguous in the loaded corpus; required (and enforced) when it "
            "is not -- e.g. Bijapur exists in both Karnataka and Chhattisgarh."
        ),
    )
    parser.add_argument(
        "--processed-root",
        type=Path,
        default=Path("data/processed"),
        help="Ingested rule base (default: data/processed).",
    )
    parser.add_argument(
        "--sowing-date",
        type=date.fromisoformat,
        help=(
            "Sowing anchor, YYYY-MM-DD. Required for dry-spell-after-sowing to be "
            "detectable at all -- it is never inferred from the weather."
        ),
    )
    parser.add_argument(
        "--onset-delay-days",
        type=int,
        help="Observed monsoon onset minus local normal. Never inferred; only IMD declares onset.",
    )
    parser.add_argument(
        "--cost-loss-ratio",
        type=float,
        default=0.20,
        help="Cost of acting / loss avoided. Sets the decision threshold (p* = alpha).",
    )
    parser.add_argument(
        "--approve-for-demo",
        action="store_true",
        help=(
            "SIMULATE reviewer approval of citation-valid rules so the emission path can "
            "be seen. Not a review. Without it every advisory correctly abstains, because "
            "no human has approved anything in the corpus."
        ),
    )
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
    seasons = range(args.start_season, args.end_season + 1)

    if args.district:
        exit_code = _run_end_to_end(args, seasons)
    else:
        artifacts = run_demo(seasons=seasons, lead_days=args.lead_days)
        print(format_report(artifacts))
        exit_code = 0

    print(f"\ntotal wall time: {time.perf_counter() - started:.1f}s")
    return exit_code


def _run_end_to_end(args: argparse.Namespace, seasons: range) -> int:
    """Rule base + weather -> advisories, for one district.

    Imported lazily so the verification path does not pay to parse the rule
    store, and so `python -m trigger_engine` still works in a checkout where
    `data/processed` has never been built.
    """
    from trigger_engine.endtoend import format_district_report, run_district
    from trigger_engine.rulestore import RuleStore
    from trigger_engine.synthetic import generate_panel

    store = RuleStore.from_processed(args.processed_root, districts={args.district})
    if not store.rules:
        print(
            f"No ingested rules found for district {args.district!r} under "
            f"{args.processed_root}. Run `make ingest-all-dacp` first, or check the "
            f"district spelling.",
            file=sys.stderr,
        )
        return 1

    matching_states = store.states_for_district(args.district)
    if args.state:
        from trigger_engine.rulestore import state_key

        if state_key(args.state) not in {state_key(s) for s in matching_states}:
            print(
                f"--state {args.state!r} does not match any loaded plan for district "
                f"{args.district!r}. Plans loaded for this district name: "
                f"{', '.join(matching_states) or '(none)'}.",
                file=sys.stderr,
            )
            return 1
        state = args.state
    elif len(matching_states) == 1:
        state = matching_states[0]
    elif len(matching_states) == 0:
        print(f"No plan found for district {args.district!r}.", file=sys.stderr)
        return 1
    else:
        print(
            f"District {args.district!r} is ambiguous: plans loaded for "
            f"{', '.join(matching_states)}. Pass --state to disambiguate -- serving the "
            f"wrong state's plan under this district name would be inventing advice.",
            file=sys.stderr,
        )
        return 1

    if args.sowing_date is None:
        print(
            "NOTE: no --sowing-date given, so `days_since_sowing` stays None and the\n"
            "      dry-spell-after-sowing condition cannot fire. That is by design: the\n"
            "      sowing anchor is never inferred from weather.\n",
            file=sys.stderr,
        )

    run = run_district(
        state,
        args.district,
        store,
        generate_panel(seasons=seasons),
        lead_days=args.lead_days,
        cost_loss_ratio=args.cost_loss_ratio,
        sowing_date=args.sowing_date,
        onset_delay_days=args.onset_delay_days,
        approve_for_demo=args.approve_for_demo,
    )

    if args.approve_for_demo:
        print(
            "WARNING: --approve-for-demo is on. Rules were marked approved by a SIMULATED\n"
            "         reviewer, not a human. Citation checks still applied. Nothing here\n"
            "         is fit to send to a farmer.\n",
            file=sys.stderr,
        )

    print(format_district_report(run))
    for line in store.coverage().summary_lines():
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
