"""Shared test fixtures for medrec tests."""

from __future__ import annotations

from datetime import date

import pytest

from pathlib import Path

from pydantic import TypeAdapter

from medrec_obsidian.models import (
    ChinesePatentMedicine,
    Diagnosis,
    FollowUpEntry,
    Herb,
    HerbalFormula,
    LabResult,
    Sex,
    VisitRecord,
    WesternMedication,
)


@pytest.fixture
def sample_visits() -> list[VisitRecord]:
    """A synthetic multi-patient, multi-visit dataset (no real patient data).

    Deliberately exercises every cross-link path:
      - a herb (桂枝) shared across all three formulas
      - a herb (甘草) shared across two formulas
      - a symptom (头痛) shared across visits/patterns
      - one doctor (李医生) across all visits
      - a multi-visit patient (张三)
      - a lab name with link-unsafe characters (谷草/谷丙比值, NEUT#)
    """
    a1 = VisitRecord(
        patient_name="张三",
        sex=Sex.MALE,
        age=40,
        visit_date=date(2026, 1, 1),
        hospital="测试医院",
        department="内科",
        registration_number="A001",
        doctor="李医生",
        source_pdf="caseA.pdf",
        source_pages=[0, 1],
        chief_complaint="头痛发热三日",
        present_illness="恶寒发热，头痛。",
        treatment_principle="辛温解表。",
        tcm_diagnoses=[Diagnosis(index=1, name="感冒"), Diagnosis(index=2, name="风寒证")],
        western_diagnoses=[Diagnosis(index=1, name="上呼吸道感染")],
        symptoms=["头痛", "发热", "咳嗽"],
        medications=[WesternMedication(name="布洛芬缓释胶囊", route="口服")],
        chinese_patent_medicines=[ChinesePatentMedicine(name="感冒清热颗粒", route="口服")],
        herbal_formulas=[
            HerbalFormula(
                formula_id="F001",
                dose_count=7,
                herbs=[
                    Herb(name="桂枝", dosage="9.00g", dosage_value=9.0),
                    Herb(name="白芍", dosage="9.00g", dosage_value=9.0),
                    Herb(name="甘草", dosage="6.00g", dosage_value=6.0),
                ],
            )
        ],
        herbs=["桂枝", "白芍", "甘草"],
        labs=[
            LabResult(
                chinese_name="白细胞计数",
                abbreviation="WBC",
                value="10.5",
                unit="*10^9/L",
                direction="↑",
                is_starred=True,
            )
        ],
        follow_ups=[
            FollowUpEntry(date_str="2026-01-08", follow_date=date(2026, 1, 8), text="复诊：热退。")
        ],
    )
    a2 = VisitRecord(
        patient_name="张三",
        sex=Sex.MALE,
        age=40,
        visit_date=date(2026, 2, 1),
        hospital="测试医院",
        department="内科",
        registration_number="A001",
        doctor="李医生",
        source_pdf="caseA.pdf",
        source_pages=[2, 3],
        chief_complaint="头痛复发",
        tcm_diagnoses=[Diagnosis(index=1, name="感冒"), Diagnosis(index=2, name="风寒证")],
        western_diagnoses=[Diagnosis(index=1, name="上呼吸道感染")],
        symptoms=["头痛"],
        herbal_formulas=[
            HerbalFormula(
                formula_id="F003",
                dose_count=5,
                herbs=[
                    Herb(name="桂枝", dosage="12.00g", dosage_value=12.0),
                    Herb(name="生姜", dosage="9.00g", dosage_value=9.0),
                ],
            )
        ],
        herbs=["桂枝", "生姜"],
    )
    b1 = VisitRecord(
        patient_name="李四",
        sex=Sex.FEMALE,
        age=55,
        visit_date=date(2026, 3, 1),
        hospital="测试医院",
        department="内科",
        registration_number="B001",
        doctor="李医生",
        source_pdf="caseB.pdf",
        source_pages=[0, 1],
        chief_complaint="咳嗽咽痛一周",
        tcm_diagnoses=[Diagnosis(index=1, name="咳嗽"), Diagnosis(index=2, name="风热证")],
        western_diagnoses=[Diagnosis(index=1, name="急性支气管炎")],
        symptoms=["咳嗽", "咽痛"],
        herbal_formulas=[
            HerbalFormula(
                formula_id="F002",
                dose_count=7,
                herbs=[
                    Herb(name="桂枝", dosage="6.00g", dosage_value=6.0),
                    Herb(name="甘草", dosage="6.00g", dosage_value=6.0),
                    Herb(name="桔梗", dosage="10.00g", dosage_value=10.0),
                ],
            )
        ],
        herbs=["桂枝", "甘草", "桔梗"],
        labs=[
            LabResult(chinese_name="谷草/谷丙比值", value="1.2"),
            LabResult(
                chinese_name="中性粒细胞绝对值",
                abbreviation="NEUT#",
                value="6.0",
                unit="*10^9/L",
                direction="↑",
            ),
        ],
    )
    return [a1, a2, b1]


@pytest.fixture
def sample_visits_json_file(sample_visits: list[VisitRecord], tmp_path: Path) -> Path:
    """Serialize the synthetic dataset to a JSON file (as `medrec update` expects)."""
    ta = TypeAdapter(list[VisitRecord])
    path = tmp_path / "extracted.json"
    path.write_bytes(ta.dump_json(sample_visits))
    return path


@pytest.fixture
def make_pdf(tmp_path: Path):
    """Factory that writes a synthetic multi-page PDF and returns its path."""
    import fitz

    def _make(pages: int = 3, name: str = "case.pdf") -> Path:
        doc = fitz.open()
        for i in range(pages):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page {i + 1}")
        path = tmp_path / name
        doc.save(str(path))
        doc.close()
        return path

    return _make


@pytest.fixture
def sample_visit_record() -> VisitRecord:
    return VisitRecord(
        patient_name="测试患者",
        sex=Sex.FEMALE,
        age=60,
        visit_date=date(2026, 5, 4),
        hospital="测试医院",
        department="内科",
        registration_number="TEST-0001",
        fee_category="自费",
        doctor="测试医生",
        chief_complaint="头晕两年，加重2月",
        present_illness="头晕，每次持续几分钟，伴恶心。",
        tcm_diagnoses=[
            Diagnosis(index=1, name="眩晕"),
            Diagnosis(index=2, name="气血亏虚证"),
        ],
        western_diagnoses=[
            Diagnosis(index=1, name="眩晕综合征"),
            Diagnosis(index=2, name="2型糖尿病"),
        ],
        symptoms=["头晕", "恶心", "胸闷", "胸痛", "口干"],
        diseases=["眩晕", "气血亏虚证", "眩晕综合征", "2型糖尿病"],
        herbal_formulas=[
            HerbalFormula(
                formula_id="T0001",
                dose_count=7,
                herbs=[
                    Herb(name="姜半夏", dosage="12.00g", dosage_value=12.0, dosage_unit="g"),
                    Herb(name="桂枝", dosage="12.00g", dosage_value=12.0, dosage_unit="g"),
                ],
            )
        ],
        herbs=["姜半夏", "桂枝"],
        source_pdf="test.pdf",
        source_pages=[0, 1],
        raw_text_by_page={0: "Page 1 text", 1: "Page 2 text"},
    )
