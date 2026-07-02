"""Tests for the Pydantic data models."""

from __future__ import annotations

from datetime import date

from pydantic import TypeAdapter

from medrec_obsidian.models import (
    Diagnosis,
    KeywordOccurrence,
    KeywordType,
    Sex,
    VisitRecord,
)


def test_visit_record_minimal():
    v = VisitRecord(patient_name="张三", visit_date=date(2026, 1, 1))
    assert v.sex == Sex.UNKNOWN
    assert v.tcm_diagnoses == []
    assert v.extraction_confidence == 1.0


def test_sex_enum_values():
    assert Sex.MALE.value == "男"
    assert Sex.FEMALE.value == "女"


def test_diagnosis_qualifier_optional():
    d = Diagnosis(index=1, name="脑梗死", qualifier="恢复期")
    assert d.qualifier == "恢复期"
    assert Diagnosis(name="眩晕").qualifier is None


def test_keyword_occurrence_fields():
    o = KeywordOccurrence(patient="张三", visit_link="张三/2026-01-01__x", visit_date="2026-01-01")
    assert o.detail == ""


def test_visit_record_list_json_roundtrip(sample_visits):
    ta = TypeAdapter(list[VisitRecord])
    raw = ta.dump_json(sample_visits)
    restored = ta.validate_json(raw)
    assert len(restored) == len(sample_visits)
    assert restored[0].patient_name == "张三"
    assert restored[0].herbal_formulas[0].formula_id == "F001"


def test_keyword_type_values():
    assert KeywordType.HERB.value == "herb"
    assert KeywordType.TCM_PATTERN.value == "tcm_pattern"
