"""CLI entry point to scrape, summarize, and push data to a Google Sheet."""

from __future__ import annotations

import argparse
import os
from typing import Dict

from aggregator.aggregator import scrape_patterns
from aggregator.gemini import GeminiSummarizer
from sheet.sheet_populator import push_pattern_sheets


def load_env_file(env_path: str = ".env") -> Dict[str, str]:
    """Lightweight .env loader; populates os.environ if keys are absent."""
    loaded: Dict[str, str] = {}
    if not os.path.exists(env_path):
        return loaded
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            loaded[key] = value
            if key not in os.environ:
                os.environ[key] = value
    return loaded


def run(spreadsheet_id: str, *, base_url: str | None = None) -> None:
    patterns = scrape_patterns(base_url=base_url)
    if not patterns:
        raise RuntimeError("No patterns were scraped; check base_url or network access.")
    summarizer = GeminiSummarizer()
    summarized = summarizer.summarize_patterns(patterns)

    # Merge summaries back onto original pattern objects.
    enriched = []
    for original, summary in zip(patterns, summarized):
        merged = dict(original)
        merged.update(summary)
        enriched.append(merged)

    # Create one tab per pattern with solved columns.
    push_pattern_sheets(spreadsheet_id, enriched, clear_first=True)


def parse_args() -> argparse.Namespace:
    load_env_file()  # make .env values available to defaults and downstream code
    parser = argparse.ArgumentParser(
        description="Scrape LeetCode patterns, summarize with Gemini, and upload to Google Sheets."
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=os.getenv("SHEET_ID"),
        required=not bool(os.getenv("SHEET_ID")),
        help="Target Google Sheet ID. Defaults to SHEET_ID from environment/.env.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("BASE_SITE"),
        help="Override base site URL. Defaults to BASE_SITE from environment/.env.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(args.spreadsheet_id, base_url=args.base_url)


if __name__ == "__main__":
    main()
