"""Shared test fixtures for medrec tests."""

from __future__ import annotations

from datetime import date

import pytest

from medrec_obsidian.models import (
    Diagnosis,
    FollowUpEntry,
    Herb,
    HerbalFormula,
    Sex,
    VisitRecord,
    WesternMedication,
    ChinesePatentMedicine,
)


@pytest.fixture
def sample_visit_record() -> VisitRecord:
    return VisitRecord(
        patient_name="测试患者",
        sex=Sex.FEMALE,
        age=60,
        visit_date=date(2026, 5, 4),
        hospital="北京中医药大学东方医院",
        department="脑病二科",
        registration_number="2604040539",
        fee_category="自费",
        doctor="方晓磊",
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
                formula_id="43622340",
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
