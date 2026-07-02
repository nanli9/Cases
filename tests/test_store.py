"""Tests for the cumulative VisitRecord store (medrec_obsidian.store)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from medrec_obsidian.models import Diagnosis, Sex, VisitRecord
from medrec_obsidian.store import (
    load_store,
    merge_visits,
    save_store,
    visit_identity,
)


def _visit(name: str, d: date, reg: str = "", pdf: str = "case.pdf", **kw) -> VisitRecord:
    return VisitRecord(
        patient_name=name,
        sex=Sex.MALE,
        visit_date=d,
        registration_number=reg,
        source_pdf=pdf,
        **kw,
    )


def test_visit_identity_tuple():
    v = _visit("张三", date(2026, 1, 1), reg="A001", pdf="caseA.pdf")
    assert visit_identity(v) == ("张三", "2026-01-01", "A001", "caseA.pdf")


def test_visit_identity_defaults_blank():
    v = VisitRecord(patient_name="李四", visit_date=date(2026, 2, 2))
    assert visit_identity(v) == ("李四", "2026-02-02", "", "")


def test_merge_dedups_and_replaces_on_same_identity():
    a = _visit("张三", date(2026, 1, 1), reg="A001", chief_complaint="旧")
    a_fixed = _visit("张三", date(2026, 1, 1), reg="A001", chief_complaint="新")
    merged = merge_visits([a], [a_fixed])
    assert len(merged) == 1
    assert merged[0].chief_complaint == "新"


def test_merge_appends_new_identities():
    a = _visit("张三", date(2026, 1, 1), reg="A001")
    b = _visit("李四", date(2026, 3, 1), reg="B001", pdf="caseB.pdf")
    merged = merge_visits([a], [b])
    assert {v.patient_name for v in merged} == {"张三", "李四"}
    assert len(merged) == 2


def test_merge_is_sorted_by_patient_then_date():
    v1 = _visit("张三", date(2026, 2, 1), reg="A001")
    v2 = _visit("张三", date(2026, 1, 1), reg="A001", pdf="caseA2.pdf")
    v3 = _visit("李四", date(2026, 3, 1), reg="B001", pdf="caseB.pdf")
    merged = merge_visits([], [v3, v1, v2])
    assert [(v.patient_name, v.visit_date) for v in merged] == [
        ("张三", date(2026, 1, 1)),
        ("张三", date(2026, 2, 1)),
        ("李四", date(2026, 3, 1)),
    ]


def test_merge_later_incoming_wins_within_batch():
    a1 = _visit("张三", date(2026, 1, 1), reg="A001", chief_complaint="一")
    a2 = _visit("张三", date(2026, 1, 1), reg="A001", chief_complaint="二")
    merged = merge_visits([], [a1, a2])
    assert len(merged) == 1
    assert merged[0].chief_complaint == "二"


def test_load_missing_returns_empty(tmp_path: Path):
    assert load_store(tmp_path / "nope.json") == []


def test_save_load_round_trip(tmp_path: Path):
    visits = [
        _visit("张三", date(2026, 1, 1), reg="A001", tcm_diagnoses=[Diagnosis(name="感冒")]),
        _visit("李四", date(2026, 3, 1), reg="B001", pdf="caseB.pdf"),
    ]
    path = tmp_path / "sub" / "records.json"
    save_store(path, visits)
    assert path.exists()
    loaded = load_store(path)
    assert loaded == visits


def test_saved_json_is_readable_utf8(tmp_path: Path):
    path = tmp_path / "records.json"
    save_store(path, [_visit("张三", date(2026, 1, 1), reg="A001")])
    # Non-ASCII names are stored raw (not \uXXXX escaped).
    assert "张三" in path.read_text(encoding="utf-8")
