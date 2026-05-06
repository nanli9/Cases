"""Utility functions: filename sanitization, fuzzy matching, date parsing, hashing."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Optional

from rapidfuzz import fuzz


def sanitize_filename(name: str) -> str:
    """Remove characters illegal in filenames and Obsidian note names.

    Strips: / \\ : * ? " < > | # ^ [ ] { }
    Replaces whitespace runs with a single space.
    Strips leading/trailing whitespace and dots.
    """
    # Remove illegal characters
    cleaned = re.sub(r'[/\\:*?"<>|#\^\[\]{}]', "", name)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Strip leading/trailing whitespace and dots
    cleaned = cleaned.strip(". ")
    return cleaned if cleaned else "unnamed"


def fuzzy_match(
    query: str, candidates: list[str], threshold: int = 85
) -> Optional[str]:
    """Find the best fuzzy match for query among candidates.

    Returns the best match above threshold, or None.
    """
    if not candidates:
        return None
    best_score = 0
    best_match = None
    for candidate in candidates:
        score = fuzz.ratio(query, candidate)
        if score > best_score:
            best_score = score
            best_match = candidate
    if best_score >= threshold:
        return best_match
    return None


def parse_chinese_date(s: str) -> Optional[date]:
    """Parse date strings in various Chinese/standard formats.

    Handles:
      - 2026-05-04
      - 2026-5-4
      - 2026年5月4日
      - 2026年05月04日
    """
    if not s:
        return None
    s = s.strip()

    # ISO-like format: 2026-05-04 or 2026-5-4
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    # Chinese format: 2026年5月4日
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    return None


def compute_content_hash(text: str) -> str:
    """Compute SHA256 hash of normalized text for deduplication."""
    normalized = re.sub(r"\s+", "", text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def count_chinese_chars(text: str) -> int:
    """Count CJK Unified Ideograph characters in text."""
    return len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))


def chinese_char_ratio(text: str) -> float:
    """Compute the ratio of CJK characters to total characters."""
    if not text:
        return 0.0
    total = len(text.strip())
    if total == 0:
        return 0.0
    return count_chinese_chars(text) / total


def today_str() -> str:
    """Return today's date as YYYY-MM-DD string."""
    return date.today().isoformat()
