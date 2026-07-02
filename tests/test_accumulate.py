"""End-to-end tests for `medrec update --append` (cumulative accumulation)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic import TypeAdapter

from medrec_obsidian.cli import main
from medrec_obsidian.config import Config
from medrec_obsidian.models import VisitRecord
from medrec_obsidian.store import load_store

from .vault_audit import find_broken_links

_TA = TypeAdapter(list[VisitRecord])


@pytest.fixture
def split_json(sample_visits, tmp_path: Path):
    """Write the synthetic dataset as two JSON files: A (张三) and B (李四)."""
    a = [v for v in sample_visits if v.patient_name == "张三"]
    b = [v for v in sample_visits if v.patient_name == "李四"]
    file_a = tmp_path / "caseA.json"
    file_b = tmp_path / "caseB.json"
    file_a.write_bytes(_TA.dump_json(a))
    file_b.write_bytes(_TA.dump_json(b))
    return file_a, file_b


def _update_append(json_file: Path, vault: Path):
    return CliRunner().invoke(
        main,
        ["update", "--from-json", str(json_file), "--vault", str(vault), "--append"],
    )


def test_append_accumulates_both_files(split_json, tmp_path: Path):
    file_a, file_b = split_json
    vault = tmp_path / "vault"
    cfg = Config()

    r1 = _update_append(file_a, vault)
    assert r1.exit_code == 0, r1.output
    r2 = _update_append(file_b, vault)
    assert r2.exit_code == 0, r2.output

    root = vault / "Medical Records"
    # Both patients present in the vault after appending the second file.
    assert (root / "Patients" / "张三.md").exists()
    assert (root / "Patients" / "李四.md").exists()
    # Visit notes from BOTH pdfs survive.
    assert (root / "Visits" / "张三" / "2026-01-01__caseA.md").exists()
    assert (root / "Visits" / "张三" / "2026-02-01__caseA.md").exists()
    assert (root / "Visits" / "李四" / "2026-03-01__caseB.md").exists()

    # The store holds the union of all three visits.
    store = load_store(cfg.records_store_path(vault))
    assert len(store) == 3
    assert {v.patient_name for v in store} == {"张三", "李四"}

    # Every link still resolves.
    assert find_broken_links(root) == {}


def test_reappending_is_idempotent(split_json, tmp_path: Path):
    file_a, file_b = split_json
    vault = tmp_path / "vault"
    cfg = Config()

    _update_append(file_a, vault)
    _update_append(file_b, vault)
    root = vault / "Medical Records"
    before = _snapshot(root)
    store_before = load_store(cfg.records_store_path(vault))

    # Re-append the same B file: no new/duplicate visits, identical notes.
    _update_append(file_b, vault)
    after = _snapshot(root)
    store_after = load_store(cfg.records_store_path(vault))

    assert len(store_after) == len(store_before) == 3
    assert before == after


def test_appending_corrected_visit_updates_not_duplicates(split_json, tmp_path: Path):
    file_a, _ = split_json
    vault = tmp_path / "vault"
    cfg = Config()

    _update_append(file_a, vault)

    # A corrected copy of an existing visit (same identity, changed field).
    a = [v for v in _TA.validate_json(file_a.read_bytes())]
    a[0].chief_complaint = "订正后的主诉ZZZ"
    corrected = tmp_path / "caseA_fixed.json"
    corrected.write_bytes(_TA.dump_json([a[0]]))

    _update_append(corrected, vault)

    store = load_store(cfg.records_store_path(vault))
    # Same identity → replaced, not duplicated.
    assert len(store) == 2
    matches = [v for v in store if v.visit_date.isoformat() == "2026-01-01"]
    assert len(matches) == 1
    assert matches[0].chief_complaint == "订正后的主诉ZZZ"

    note = (vault / "Medical Records" / "Visits" / "张三" / "2026-01-01__caseA.md").read_text(
        encoding="utf-8"
    )
    assert "订正后的主诉ZZZ" in note


def _snapshot(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in root.rglob("*.md")
        if ".obsidian" not in p.parts
    }
