"""Scrape LeetCode patterns data from the configured base site.

Primary entrypoint: `scrape_patterns(base_url=None, session=None) -> list[dict]`.
Returns dictionaries in the shape expected by `GeminiSummarizer`:
{
    "pattern": str,
    "url": str,
    "problems": [{"title": str, "difficulty": str, "url": str}, ...],
    "notes": str,
}
"""

from __future__ import annotations

import json
import os
import re
from html import unescape
from typing import Any, Dict, Iterable, List, Mapping, MutableSequence, Sequence

import requests


DEFAULT_BASE_SITE = "https://seanprashad.com/leetcode-patterns/"
FALLBACK_PATTERNS_URL = (
    "https://raw.githubusercontent.com/SeanPrashad/leetcode-patterns/master/src/data/leetcode-patterns.json"
)


def scrape_patterns(
    base_url: str | None = None,
    *,
    session: requests.Session | None = None,
    allow_fallback: bool = True,
    fallback_url: str | None = None,
) -> List[Dict[str, Any]]:
    """Fetch and normalize patterns from the target site."""
    base_url = base_url or load_base_site()
    sess = session or requests.Session()
    html = fetch_html(sess, base_url)

    next_data = extract_next_data(html)
    patterns = extract_patterns_from_next_data(next_data) if next_data else []

    if not patterns:
        patterns = extract_patterns_from_html(html)

    if not patterns and allow_fallback:
        patterns = fetch_fallback_patterns(sess, fallback_url=fallback_url)

    normalized = [normalize_pattern(entry, base_url) for entry in patterns]
    return [p for p in normalized if p["pattern"] and p["problems"]]


def load_base_site(env_path: str = ".env") -> str:
    """Load BASE_SITE from env or .env fallback."""
    env_val = os.getenv("BASE_SITE")
    if env_val:
        return env_val
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("BASE_SITE"):
                    _, value = line.split("=", 1)
                    return value.strip().strip('"').strip("'")
    return DEFAULT_BASE_SITE


def fetch_html(session: requests.Session, url: str) -> str:
    """Fetch raw HTML from the base site."""
    headers = {
        "User-Agent": "leetcode-patterns-aggregator/0.1 (+https://github.com/)",
    }
    resp = session.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_next_data(html: str) -> Any | None:
    """Pull the __NEXT_DATA__ payload if present (common for Next.js sites)."""
    match = re.search(
        r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if not match:
        return None
    script_body = unescape(match.group(1))
    try:
        return json.loads(script_body)
    except json.JSONDecodeError:
        return None


def extract_patterns_from_next_data(next_data: Any) -> List[Mapping[str, Any]]:
    """Search recursively for a list of pattern objects in Next.js data."""
    patterns: List[Mapping[str, Any]] = []

    def looks_like_pattern_list(node: Any) -> bool:
        return bool(
            isinstance(node, list)
            and node
            and all(
                isinstance(item, dict)
                and any(k in item for k in ("pattern", "name", "title"))
                and ("problems" in item or "questions" in item)
                for item in node
            )
        )

    def walk(node: Any):
        nonlocal patterns
        if patterns:
            return
        if looks_like_pattern_list(node):
            patterns = node  # type: ignore[assignment]
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if "patterns" in node and looks_like_pattern_list(node["patterns"]):
                patterns = node["patterns"]  # type: ignore[assignment]
                return
            if "leetcodePatterns" in node and looks_like_pattern_list(
                node["leetcodePatterns"]
            ):
                patterns = node["leetcodePatterns"]  # type: ignore[assignment]
                return
            for value in node.values():
                walk(value)

    walk(next_data)
    return patterns


def extract_patterns_from_html(html: str) -> List[Mapping[str, Any]]:
    """Fallback HTML scraping when __NEXT_DATA__ is not present.

    Heuristic: looks for header tags (<h2>/<h3>) followed by <li> items.
    """
    pattern_blocks: List[Dict[str, Any]] = []
    header_iter = re.finditer(r"<h[23][^>]*>(.*?)</h[23]>", html, re.IGNORECASE | re.DOTALL)
    headers = [unescape(strip_tags(m.group(1))).strip() for m in header_iter]

    # Split the page into segments after each header for basic association.
    segments = re.split(r"<h[23][^>]*>.*?</h[23]>", html, flags=re.IGNORECASE | re.DOTALL)
    for name, segment in zip(headers, segments[1:]):  # first split is pre-header noise
        problems = []
        for li in re.finditer(r"<li[^>]*>(.*?)</li>", segment, re.IGNORECASE | re.DOTALL):
            text = unescape(strip_tags(li.group(1))).strip()
            if not text:
                continue
            problems.append({"title": text, "difficulty": "Unknown", "url": ""})
        if name and problems:
            pattern_blocks.append({"pattern": name, "problems": problems})

    return pattern_blocks


def normalize_pattern(entry: Mapping[str, Any], base_url: str) -> Dict[str, Any]:
    """Normalize scraped entry to the expected shape."""
    name = entry.get("pattern") or entry.get("name") or entry.get("title") or ""
    url = (
        entry.get("url")
        or entry.get("link")
        or f"{base_url.rstrip('/')}/{slugify(name)}" if name else base_url
    )
    notes = entry.get("notes") or entry.get("description") or entry.get("summary") or ""
    problems = normalize_problems(entry.get("problems") or entry.get("questions") or [])
    return {"pattern": name, "url": url, "problems": problems, "notes": notes}


def normalize_problems(problems: Iterable[Mapping[str, Any]]) -> List[Dict[str, str]]:
    """Normalize problem entries, keeping title/difficulty/url."""
    normalized: List[Dict[str, str]] = []
    for p in problems:
        title = p.get("title") or p.get("name") or p.get("question") or "Unknown Problem"
        difficulty = p.get("difficulty") or p.get("level") or p.get("tier") or "Unknown"
        url = p.get("url") or p.get("link") or p.get("leetcode_url") or ""
        normalized.append({"title": title, "difficulty": difficulty, "url": url})
    return normalized


def strip_tags(raw_html: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", " ", raw_html)


def slugify(value: str) -> str:
    """Very small slugifier; lowercases and replaces spaces with hyphens."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def fetch_fallback_patterns(
    session: requests.Session, *, fallback_url: str | None = None
) -> List[Mapping[str, Any]]:
    """Fetch patterns from a known JSON source as a fallback."""
    url = fallback_url or os.getenv("FALLBACK_PATTERNS_URL") or FALLBACK_PATTERNS_URL
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


__all__ = [
    "scrape_patterns",
    "load_base_site",
    "extract_next_data",
    "extract_patterns_from_next_data",
    "extract_patterns_from_html",
    "fetch_fallback_patterns",
    "normalize_pattern",
    "normalize_problems",
    "slugify",
]
