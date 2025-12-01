"""CLI entry point to scrape, summarize, and push data to a Google Sheet."""

from __future__ import annotations

import argparse
import os
from typing import Dict, List

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
        raise RuntimeError(
            "No patterns were scraped; check base_url, network access, or provide FALLBACK_PATTERNS_FILE."
        )
    summarizer = GeminiSummarizer()
    summarized = summarizer.summarize_patterns(patterns)

    # Merge summaries back onto original pattern objects.
    enriched = []
    for original, summary in zip(patterns, summarized):
        merged = dict(original)
        merged.update(summary)
        enriched.append(merged)

    resources_rows = build_resources_rows(summarizer, enriched)

    # Create one tab per pattern with solved columns + resources tab.
    push_pattern_sheets(spreadsheet_id, enriched, clear_first=True, resources_rows=resources_rows)


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


def build_resources_rows(summarizer: GeminiSummarizer, patterns: List[Dict]) -> List[List[str]]:
    """Build a resources sheet with curated links and Gemini-generated hints."""
    resources = [
        {
            "name": "LeetCode Patterns (Sean Prashad)",
            "type": "Patterns",
            "link": "https://seanprashad.com/leetcode-patterns/",
            "notes": "Canonical patterns list with curated ordering.",
        },
        {
            "name": "NeetCode Roadmap",
            "type": "Video Series",
            "link": "https://neetcode.io/roadmap",
            "notes": "Structured topic order with explanations and code.",
        },
        {
            "name": "NeetCode 150 (LeetCode list)",
            "type": "Practice List",
            "link": "https://leetcode.com/studyplan/neetcode-150/",
            "notes": "Concise must-do problems across topics.",
        },
        {
            "name": "USACO Guide (General Techniques)",
            "type": "Reading",
            "link": "https://usaco.guide",
            "notes": "Good deep dives on data structures/techniques.",
        },
        {
            "name": "CP Handbook (KACTL)",
            "type": "Reference",
            "link": "https://kactl.io/",
            "notes": "Short implementations and explanations for advanced topics.",
        },
    ]

    hints = [
        "Prove monotonicity before binary search; test mid bias and termination carefully.",
        "For sliding window, define what makes a window valid and how to shrink.",
        "For DP, write state, transition, base case; test small n; consider memory optimize.",
        "Monotonic stack: store indices; think 'next greater/smaller' patterns.",
        "Graph cycles: DFS colors or union-find; for DAG order use topo sort.",
        "Heaps: when you need top-k or running best; min-heap vs max-heap tradeoffs.",
        "Trie for prefix problems; store counts/ends to speed lookups.",
        "Union-Find: path compression + union by rank; useful for connectivity and Kruskal.",
        "Prefix sums/diffs: convert range updates/queries to O(1).",
    ]

    # Try to get Gemini to add 5 more concise study tips tailored to current patterns.
    try:
        pattern_names = ", ".join(p.get("pattern", "") for p in patterns[:12])
        prompt = (
            "Give 5 concise LeetCode study tips tailored to these patterns: "
            f"{pattern_names}. Keep each tip under 90 chars, no numbering."
        )
        resp = summarizer._generate_with_fallback(prompt, temperature=0.2)  # type: ignore[attr-defined]
        text = resp.text if hasattr(resp, "text") else ""
        for line in text.splitlines():
            tip = line.strip("-• ").strip()
            if tip:
                hints.append(tip)
    except Exception:
        pass

    rows: List[List[str]] = []
    rows.append(["Resources", "Type", "Link", "Notes"])
    for r in resources:
        rows.append([r["name"], r["type"], r["link"], r["notes"]])
    rows.append([])
    rows.append(["Techniques & Hints"])
    rows.append(["Hint"])
    for h in hints:
        rows.append([h])
    return rows


if __name__ == "__main__":
    main()
