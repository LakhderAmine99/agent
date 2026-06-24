#!/usr/bin/env python3
"""
Generic Fetch Agent
Reads catalog/*.json recipes and fetches data from external sources.

Usage:
  python agent.py --source wikipedia --articles "Inflation,Housing_market" --start 2020-01-01 --end 2024-12-31 --output-both
  python agent.py --source imf --indicators "NGDP_RPCH,LUR" --countries "US,GB,DE" --output-json
  python agent.py --source ofac --filter "program=RUSSIA" --stdout-json
"""

import argparse
import json
import sys
from pathlib import Path

from output import emit_output
from sources import FETCHERS
from sources.base import log

CATALOG_DIR = Path(__file__).parent / "catalog"
VALID_SOURCES = list(FETCHERS.keys())


def load_recipe(source_id):
    """Load recipe JSON from catalog/{source_id}.json."""
    recipe_path = CATALOG_DIR / f"{source_id}.json"
    if not recipe_path.exists():
        raise FileNotFoundError(f"Recipe not found: {recipe_path}")
    with open(recipe_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_params(source_id, recipe, args):
    """Validate CLI params against recipe cli_parameters."""
    cli_params = recipe.get("cli_parameters", {})
    required = cli_params.get("required", [])

    param_map = {
        "articles": args.articles,
        "indicators": args.indicators,
        "countries": args.countries,
        "category": args.category,
        "keyword": args.keyword,
        "filter": args.filter,
    }

    for req in required:
        if not param_map.get(req):
            raise ValueError(
                f"--{req} is required for {source_id} source. "
                f"See catalog/{source_id}.json for details."
            )


def build_params(args):
    """Build params dict from CLI args."""
    return {
        "articles": args.articles,
        "indicators": args.indicators,
        "countries": args.countries,
        "start": args.start,
        "end": args.end,
        "category": args.category,
        "keyword": args.keyword,
        "max_results": args.max_results,
        "filter": args.filter,
    }


def main():
    parser = argparse.ArgumentParser(description="Generic Fetch Agent")
    parser.add_argument(
        "--source", required=True, choices=VALID_SOURCES,
        help="Data source to fetch from",
    )

    # Source-specific parameters
    parser.add_argument("--articles", help="Comma-separated Wikipedia article titles")
    parser.add_argument("--indicators", help="Comma-separated indicator codes")
    parser.add_argument("--countries", help="Comma-separated country codes or 'all'")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD or YYYY)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD or YYYY)")
    parser.add_argument("--category", help="arXiv category code")
    parser.add_argument("--keyword", help="Keyword for arXiv abstract search")
    parser.add_argument("--max-results", type=int, default=100, help="Max arXiv results")
    parser.add_argument("--filter", help="OFAC filter (e.g. program=RUSSIA)")

    # Output modes
    parser.add_argument("--output-csv", action="store_true", help="Write CSV file")
    parser.add_argument("--output-json", action="store_true", help="Write JSON file")
    parser.add_argument("--stdout-json", action="store_true", help="Print JSON to stdout")
    parser.add_argument("--output-both", action="store_true", help="Write CSV and JSON files")
    parser.add_argument("--output-dir", default="./data", help="Output directory")

    args = parser.parse_args()

    # Default to CSV if no output mode specified
    if not any([args.output_csv, args.output_json, args.stdout_json, args.output_both]):
        args.output_csv = True

    try:
        recipe = load_recipe(args.source)
        validate_params(args.source, recipe, args)

        source_name = recipe["source"]["name"]
        log(f"\n{'='*60}")
        log(f"Running: {source_name}")
        log(f"{'='*60}")

        params = build_params(args)
        fetcher = FETCHERS[args.source]
        rows = fetcher(recipe, params)

        if not rows:
            log(f"\nNo data retrieved for {source_name}")
            sys.exit(1)

        result = emit_output(
            rows,
            source_id=args.source,
            output_dir=args.output_dir,
            output_csv=args.output_csv,
            output_json=args.output_json,
            stdout_json=args.stdout_json,
            output_both=args.output_both,
            parameters=params,
        )

        log(f"\nDone: {result['count']} records")
        if result["csv"]:
            log(f"  CSV:  {result['csv']}")
        if result["json"]:
            log(f"  JSON: {result['json']}")

        sys.exit(0)

    except (ValueError, FileNotFoundError) as e:
        log(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
