"""CLI entry point to scrape, summarize, and push data to a Google Sheet."""

from __future__ import annotations

import argparse

from aggregator.aggregator import scrape_patterns
from aggregator.gemini import GeminiSummarizer
from sheet.sheet_populator import push_rows


def run(spreadsheet_id: str, range_name: str, *, base_url: str | None = None) -> None:
    patterns = scrape_patterns(base_url=base_url)
    summarizer = GeminiSummarizer()
    summarized = summarizer.summarize_patterns(patterns)
    push_rows(spreadsheet_id, range_name, summarized, clear_first=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape LeetCode patterns, summarize with Gemini, and upload to Google Sheets."
    )
    parser.add_argument("--spreadsheet-id", required=True, help="Target Google Sheet ID.")
    parser.add_argument(
        "--range-name",
        default="Sheet1!A1",
        help="Target range (e.g., 'Sheet1!A1'). Defaults to Sheet1!A1.",
    )
    parser.add_argument("--base-url", default=None, help="Override base site URL.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(args.spreadsheet_id, args.range_name, base_url=args.base_url)


if __name__ == "__main__":
    main()
