"""Link-integrity audit for a generated Obsidian vault.

Used by the test suite to guarantee that every [[wikilink]] in a freshly
built vault resolves to a real note — the exact failure mode that made the
graph look connected while every topic→visit link was actually broken.
"""

from __future__ import annotations

import re
from pathlib import Path

_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def find_broken_links(root: Path) -> dict[str, int]:
    """Return a map of unresolved wikilink target -> occurrence count.

    An empty dict means every link resolves. `root` is the vault root
    (e.g. ``<vault>/Medical Records``). Notes under ``.obsidian`` are ignored.

    Resolution mirrors Obsidian: a link resolves if it matches a note's
    basename, its full vault-relative path, or a trailing path segment
    (``folder/note``). Alias syntax (``[[x|y]]`` / table-escaped ``[[x\\|y]]``)
    and heading refs (``[[x#h]]``) are handled.
    """
    mds = [p for p in root.rglob("*.md") if ".obsidian" not in p.parts]
    basenames = {p.stem for p in mds}
    relpaths = {p.relative_to(root).with_suffix("").as_posix() for p in mds}

    broken: dict[str, int] = {}
    for p in mds:
        for m in _LINK_RE.finditer(p.read_text(encoding="utf-8")):
            target = re.split(r"\\?\|", m.group(1))[0].strip()
            # Only treat '#' as a heading ref when the raw target isn't itself a file.
            if target not in basenames and target not in relpaths:
                target = target.split("#")[0].strip()
            if not target:
                continue
            resolved = (
                target in basenames
                or target in relpaths
                or any(rp.endswith("/" + target) for rp in relpaths)
            )
            if not resolved:
                broken[target] = broken.get(target, 0) + 1
    return broken
