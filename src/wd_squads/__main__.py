"""Command line entry point: ``python -m wd_squads`` / ``wd-squads``."""

from __future__ import annotations

import argparse
import logging
import sys

from .app import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wd-squads",
        description=(
            "Compare football squads on Wikipedia with membership data (P54) on "
            "Wikidata and generate a TODO list of suggested Wikidata edits."
        ),
    )
    parser.add_argument(
        "-c", "--config", default="config/teams.yaml", help="Path to the YAML config."
    )
    parser.add_argument(
        "--reports-dir", default="reports", help="Directory for the Markdown reports."
    )
    parser.add_argument(
        "--docs-dir", default="docs", help="Directory for the HTML dashboard + JSON."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Only process the first N teams (testing)."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        results = run(
            config_path=args.config,
            reports_dir=args.reports_dir,
            docs_dir=args.docs_dir,
            limit=args.limit,
        )
    except Exception as exc:  # pragma: no cover - top level guard
        logging.error("Run failed: %s", exc)
        return 1

    total = sum(len(r.suggestions) for r in results)
    print(f"Done: {len(results)} teams, {total} suggested edits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
