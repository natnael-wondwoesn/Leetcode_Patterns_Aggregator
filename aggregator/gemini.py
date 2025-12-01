"""Gemini helpers for turning scraped LeetCode pattern data into sheet-ready rows.

Expected scraped data shape (dict per pattern):
{
    "pattern": "Sliding Window",
    "url": "https://seanprashad.com/leetcode-patterns/sliding-window",
    "problems": [
        {"title": "Best Time to Buy and Sell Stock", "difficulty": "Easy", "url": "..."},
        {"title": "Longest Substring Without Repeating Characters", "difficulty": "Medium", "url": "..."},
    ],
    "notes": "Optional free-form notes from the scraper."
}

The functions below will summarize each pattern into concise descriptions that can
be passed directly to the sheet_populator module for upload.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Sequence

from google import genai

DEFAULT_MODEL = "gemini-1.5-flash"
DEFAULT_TEMPERATURE = 0.35


class GeminiSummarizer:
    """Wraps the Gemini client and provides helpers to summarize patterns."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API key missing. Set GOOGLE_API_KEY or pass api_key explicitly."
            )
        self.model = model
        self.client = genai.Client(api_key=self.api_key)

    def summarize_patterns(
        self,
        scraped_patterns: Sequence[Mapping[str, Any]],
        *,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> List[Dict[str, str]]:
        """Summarize scraped patterns into concise sheet-ready dictionaries.

        Returns a list of dicts with:
        {
            "pattern": pattern name,
            "url": source url,
            "summary": 1–2 sentence description of the pattern,
            "top_problems": short bullet list (as text) of 3 representative problems,
        }
        """
        results: List[Dict[str, str]] = []
        for pattern in scraped_patterns:
            results.append(
                self._summarize_single(pattern, temperature=temperature),
            )
        return results

    def _summarize_single(
        self, pattern: Mapping[str, Any], *, temperature: float
    ) -> Dict[str, str]:
        pattern_name = pattern.get("pattern") or "Unknown Pattern"
        problems = pattern.get("problems") or []
        notes = pattern.get("notes") or ""
        url = pattern.get("url") or ""

        prompt = build_prompt(pattern_name, problems, notes)
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            generation_config={"temperature": temperature},
        )

        summary_text = response.text.strip() if hasattr(response, "text") else ""
        return {
            "pattern": pattern_name,
            "url": url,
            "summary": summary_text,
            "top_problems": format_problems(problems),
        }


def build_prompt(
    pattern_name: str, problems: Sequence[Mapping[str, Any]], notes: str | None
) -> str:
    """Create a concise instruction prompt for Gemini."""
    problems_text = "\n".join(
        f"- {p.get('title', 'Unknown title')} ({p.get('difficulty', 'N/A')})"
        for p in problems[:8]
    )
    return (
        f"You are summarizing a LeetCode pattern for a study sheet.\n"
        f"Pattern: {pattern_name}\n"
        f"Context: {notes or 'No extra notes provided.'}\n"
        f"Representative problems:\n{problems_text or '- No problems listed.'}\n\n"
        "Write a crisp 1-2 sentence description that explains the core idea, when to use it, "
        "and the intuition a learner should remember. Avoid verbosity and avoid code. "
        "Keep it under 420 characters."
    )


def format_problems(problems: Sequence[Mapping[str, Any]]) -> str:
    """Render up to 3 representative problems as a short bullet list string."""
    formatted = []
    for p in problems[:3]:
        title = p.get("title", "Unknown title")
        difficulty = p.get("difficulty", "N/A")
        url = p.get("url") or ""
        formatted.append(f"- {title} ({difficulty}) {url}".strip())
    return "\n".join(formatted) if formatted else "-"


__all__ = ["GeminiSummarizer", "build_prompt", "format_problems"]
