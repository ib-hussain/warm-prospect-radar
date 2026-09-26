#!/usr/bin/env python3
"""Populate the configured backend by acquiring well-known company Wikipedia pages."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings  # noqa: E402
from src.database import build_repository  # noqa: E402
from src.scraper import BusinessScrapePipeline, PipelineError  # noqa: E402

DEFAULT_COMPANIES = (
    "Apple Inc.",
    "Microsoft",
    "Amazon (company)",
    "Alphabet Inc.",
    "Meta Platforms",
    "Nvidia",
    "Tesla, Inc.",
    "JPMorgan Chase",
    "Walmart",
    "The Coca-Cola Company",
)


def wikipedia_url(title: str) -> str:
    return f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='(),._-')}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", action="append", help="Wikipedia article title; repeatable")
    parser.add_argument("--limit", type=int, default=len(DEFAULT_COMPANIES))
    parser.add_argument("--no-llm", action="store_true", help="Use deterministic extraction only")
    parser.add_argument(
        "--list-only", action="store_true", help="Print targets without acquiring them"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    companies = tuple(args.company or DEFAULT_COMPANIES)[: max(0, args.limit)]
    if args.list_only:
        for company in companies:
            print(f"{company}: {wikipedia_url(company)}")
        return 0
    if args.no_llm:
        os.environ["ENABLE_LLM"] = "false"

    settings = Settings.from_env()
    repository = build_repository(settings)
    flags = repository.get_feature_flags()
    if not flags.acquisition_enabled:
        print("Acquisition is disabled in central feature controls.", file=sys.stderr)
        return 2
    settings = replace(
        settings,
        enable_llm=settings.enable_llm and flags.llm_enabled,
        scraper_social_profile_limit=(
            settings.scraper_social_profile_limit if flags.social_acquisition_enabled else 0
        ),
    )
    pipeline = BusinessScrapePipeline(settings, repository)
    completed = 0
    print(f"Backend: {repository.backend_name}; targets: {len(companies)}")
    for index, title in enumerate(companies, start=1):
        url = wikipedia_url(title)
        print(f"[{index}/{len(companies)}] Acquiring {title} ...", flush=True)
        try:
            business, run = pipeline.run(url, business_name=title.replace(" (company)", ""))
            completed += 1
            print(
                f"  saved {business.name} | pages={run.pages_succeeded}/{run.pages_attempted} "
                f"| likelihood={business.prospect_likelihood:.1f} | score={business.prospect_score:.1f}"
            )
        except PipelineError as exc:
            print(f"  failed: {exc}", file=sys.stderr)
    print(f"Finished: {completed}/{len(companies)} businesses saved.")
    return 0 if completed or not companies else 1


if __name__ == "__main__":
    raise SystemExit(main())
