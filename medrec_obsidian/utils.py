"""Utility functions: filename sanitization, fuzzy matching, date parsing, hashing."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Optional


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


# Characters that break Obsidian wikilinks or filenames, mapped to full-width
# equivalents that are legal in both and keep the text readable.
_LINK_UNSAFE = {
    "/": "／", "\\": "＼", "#": "＃", "|": "｜", ":": "：",
    "[": "［", "]": "］", "^": "＾", "<": "＜", ">": "＞",
    "*": "＊", "?": "？", '"': "＂", "{": "｛", "}": "｝",
}


def link_safe(name: str) -> str:
    """Make a term safe to use as both a note name and a wikilink target.

    Replaces characters that Obsidian treats specially (#, /, |, etc.) with
    full-width equivalents so the note filename and every [[link]] to it match.
    """
    for bad, good in _LINK_UNSAFE.items():
        name = name.replace(bad, good)
    return name


def fuzzy_match(
    query: str, candidates: list[str], threshold: int = 85
) -> Optional[str]:
    """Find the best fuzzy match for query among candidates.

    Returns the best match above threshold, or None.
    """
    from rapidfuzz import fuzz  # optional dependency, imported lazily

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


def visit_note_link(patient_name: str, visit_date_iso: str, source_pdf: str) -> str:
    """Return the vault-relative wikilink target for a visit note.

    Matches the path written by the writer: Visits/<patient>/<date>__<pdf_stem>.md
    Obsidian resolves this partial path to the correct note.
    """
    stem = Path(source_pdf).stem if source_pdf else "unknown"
    return f"{sanitize_filename(patient_name)}/{visit_date_iso}__{sanitize_filename(stem)}"


def formula_note_name(formula_id: str, patient_name: str, visit_date_iso: str) -> str:
    """Return the note name (and wikilink target) for a herbal formula.

    Uses the prescription id when available (unique per prescription), else a
    patient/date fallback. Prefixed with 方- so the node reads clearly in the graph.
    """
    if formula_id:
        return f"方-{sanitize_filename(formula_id)}"
    return f"方-{sanitize_filename(patient_name)}-{visit_date_iso}"
