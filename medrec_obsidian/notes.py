"""Note writing that preserves a user's manual edits across regenerations.

The vault is a projection of the extracted data, so most of every note is
regenerated each run. Two things a user may add by hand are preserved:

  (a) User frontmatter keys the generator does not emit, plus the reference
      keys 性味 / 归经 / 功效分类 when the user has filled them in (the
      generator emits those blank on herb notes as a study template).
  (b) A free-text ``## 笔记`` section, re-appended verbatim to the body.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

REFERENCE_KEYS = frozenset({"性味", "归经", "功效分类"})
USER_HEADING = "## 笔记"


def _nonempty(value) -> bool:
    """True if a frontmatter value carries real content (not ``''``/``[]``/None)."""
    return value not in (None, "", [], {})


def _extract_user_section(body: str, user_heading: str) -> Optional[str]:
    """Return the user section (heading line → next sibling ``## `` / EOF), or None."""
    lines = body.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.strip() == user_heading:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    section = "\n".join(lines[start:end]).rstrip()
    return section or None


def parse_existing_note(
    path: Path, user_heading: str = USER_HEADING
) -> tuple[dict, Optional[str]]:
    """Parse an existing note into ``(frontmatter, user_section)``.

    Robust to files without frontmatter or with malformed YAML: returns
    ``({}, ...)`` for the frontmatter in those cases. ``user_section`` is the
    verbatim ``## 笔记`` block if present, else ``None``.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}, None

    old_fm: dict = {}
    body = text
    if text.startswith("---\n") or text.startswith("---\r\n"):
        parts = text.split("\n")
        end = None
        for i in range(1, len(parts)):
            if parts[i].strip() == "---":
                end = i
                break
        if end is not None:
            fm_text = "\n".join(parts[1:end])
            try:
                loaded = yaml.safe_load(fm_text)
            except yaml.YAMLError:
                loaded = None
            if isinstance(loaded, dict):
                old_fm = loaded
            body = "\n".join(parts[end + 1 :])

    return old_fm, _extract_user_section(body, user_heading)


def render_note(frontmatter: dict, title: str, body_lines: list[str]) -> str:
    """Render a note to its final markdown string (frontmatter + title + body)."""
    yaml_block = yaml.dump(
        frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False
    ).strip()
    body_text = "\n".join(body_lines).rstrip("\n")
    if body_text:
        return f"---\n{yaml_block}\n---\n\n# {title}\n\n{body_text}\n"
    return f"---\n{yaml_block}\n---\n\n# {title}\n"


def write_note_preserving(
    path: Path,
    frontmatter: dict,
    title: str,
    body_lines: list[str],
    reference_keys: frozenset[str] = REFERENCE_KEYS,
    user_heading: str = USER_HEADING,
) -> bool:
    """Write a note, merging any preserved user content when it already exists.

    Returns True if the file was newly created, False if it already existed.
    Generated frontmatter keys keep their generated position; a filled-in
    reference key keeps the user's value; unknown user keys are appended after
    the generated ones. A preserved ``## 笔记`` section is re-appended to the
    body (never duplicated).
    """
    is_new = not path.exists()
    old_fm: dict = {}
    user_section: Optional[str] = None
    if not is_new:
        old_fm, user_section = parse_existing_note(path, user_heading)

    merged: dict = {}
    for key, value in frontmatter.items():
        if key in reference_keys and key in old_fm and _nonempty(old_fm[key]):
            merged[key] = old_fm[key]
        else:
            merged[key] = value
    for key, value in old_fm.items():
        if key not in frontmatter:
            merged[key] = value

    body = list(body_lines)
    if user_section and user_heading not in "\n".join(body):
        body += ["", user_section.rstrip("\n")]

    content = render_note(merged, title, body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return is_new
