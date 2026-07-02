"""Cumulative master store of VisitRecords.

Persists the union of all visits ever extracted so that processing an
additional PDF can *merge* into the store (rather than replacing the vault
with only the latest file's data). The vault is then regenerated from the
full union, which re-aggregates every patient/topic/formula note correctly.

The store lives inside the (gitignored) vault so patient data stays local.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from .models import VisitRecord

_VisitListAdapter = TypeAdapter(list[VisitRecord])


def visit_identity(v: VisitRecord) -> tuple[str, str, str, str]:
    """Return a stable identity tuple for a visit.

    Two extractions of the same underlying visit share this identity, so an
    incoming record can replace (correct) a stored one instead of duplicating.
    """
    return (
        v.patient_name,
        v.visit_date.isoformat(),
        v.registration_number or "",
        v.source_pdf or "",
    )


def merge_visits(
    existing: list[VisitRecord], incoming: list[VisitRecord]
) -> list[VisitRecord]:
    """Merge ``incoming`` visits into ``existing``, deduped by identity.

    An incoming visit REPLACES an existing one sharing its ``visit_identity``
    (so re-extractions / corrections win). The returned union is sorted by
    ``(patient_name, visit_date)`` for deterministic output.
    """
    by_id: dict[tuple[str, str, str, str], VisitRecord] = {
        visit_identity(v): v for v in existing
    }
    for v in incoming:
        by_id[visit_identity(v)] = v
    return sorted(by_id.values(), key=lambda v: (v.patient_name, v.visit_date))


def load_store(path: Path) -> list[VisitRecord]:
    """Load the visit store from ``path`` (returns ``[]`` if the file is missing)."""
    if not path.exists():
        return []
    return _VisitListAdapter.validate_json(path.read_bytes())


def save_store(path: Path, visits: list[VisitRecord]) -> None:
    """Serialize ``visits`` to ``path`` as a UTF-8 JSON array (indent=2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_VisitListAdapter.dump_json(visits, indent=2))
