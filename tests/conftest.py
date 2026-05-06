"""Shared test fixtures for medrec tests."""

from __future__ import annotations

from datetime import date

import pytest

from medrec_obsidian.models import (
    Diagnosis,
    FollowUpEntry,
    Herb,
    HerbalFormula,
    PageHeader,
    PageText,
    Sex,
    VisitRecord,
    WesternMedication,
    ChinesePatentMedicine,
)


@pytest.fixture
def sample_page_header() -> PageHeader:
    return PageHeader(
        patient_name="测试患者",
        sex=Sex.FEMALE,
        age=60,
        visit_date=date(2026, 5, 4),
        department="脑病二科（神经内 门诊号:2604040539 科2)门诊",
        registration_number="2604040539",
        fee_category="自费",
        document_id="DFYY-MZ-20260001",
        doctor_name="方晓磊",
        page_number_in_record=1,
    )


@pytest.fixture
def sample_page_text_1(sample_page_header: PageHeader) -> PageText:
    return PageText(
        pdf_page_index=0,
        header=sample_page_header,
        body_text=(
            "*主 诉:头晕两年，加重2月\n"
            "*现 病 史:头晕，每次持续几分钟，伴恶心。无听力下降。"
            "晚上睡觉时胸闷胸痛。患者两颧、唇色红。口干，大便可。喜热饮。\n"
            "*既 往 史:慢性病史：无/有 糖尿病史2年，服用二甲双胍，注射胰岛素\n"
            "传染病史：无/有 否认\n"
            "手术、外伤史：无/有 否认\n"
            "*过 敏 史:否认/有 否认\n"
            "*个 人 史:无特殊\n"
            "*家 族 史:无特殊\n"
            "生命体征:BP：117/67 mmHg\n"
        ),
        extraction_method="text_layer",
        confidence=1.0,
    )


@pytest.fixture
def sample_page_text_2(sample_page_header: PageHeader) -> PageText:
    header2 = sample_page_header.model_copy(update={"page_number_in_record": 2})
    return PageText(
        pdf_page_index=1,
        header=header2,
        body_text=(
            "体格检查:神志正常，面色如常，形体正常，行动自如。\n"
            "中医四诊: 舌象: 舌质淡嫩  脉象: 左寸沉弱\n"
            "辨证依据:结合患者四诊信息考虑\n"
            "治则治法:随证治之。\n"
            "辅助检查:（单击鼠标右键选择\u201c引数据\u201d可引用一月内相关辅助检验结果）\n"
            "初步诊断:中医诊断：\n"
            "1.眩晕  2.气血亏虚证\n"
            "西医诊断：\n"
            "1.眩晕综合征  2.2型糖尿病\n"
            "处 置:检查：\n"
            "1.生化（22）  360\n"
            "草药方 43622340 贴数：7\n"
            "姜半夏12.00g  桂枝12.00g  茯苓30.00g  麸炒白术15.00g\n"
            "黄芩片15.00g  黄芪45.00g  黄连片15.00g  熟地黄40.00g\n"
            "中成药处方\n"
            "天丹通络片(0.415g*60片) 2.00盒/片 三次/日 (9-15-21) 5(片) 口服\n"
            "注意事项:嘱患者按医嘱规律用药，不适随诊，定期门诊复诊。\n"
        ),
        extraction_method="text_layer",
        confidence=1.0,
    )


@pytest.fixture
def sample_page_text_duplicate(sample_page_text_1: PageText) -> PageText:
    """A duplicate of page 1 (simulating the 郑雯兮 duplicate issue)."""
    return PageText(
        pdf_page_index=3,
        header=sample_page_text_1.header.model_copy(),
        body_text=sample_page_text_1.body_text,
        extraction_method="text_layer",
        confidence=1.0,
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


@pytest.fixture
def multi_visit_headers() -> list[PageHeader]:
    """Page headers simulating 杨玉环's two visits."""
    base = {
        "patient_name": "多次就诊",
        "sex": Sex.FEMALE,
        "age": 79,
        "department": "脑病二科",
        "registration_number": "2604110938",
        "fee_category": "医保持卡",
        "doctor_name": "方晓磊",
    }
    return [
        PageHeader(**base, visit_date=date(2026, 4, 20), page_number_in_record=1),
        PageHeader(**base, visit_date=date(2026, 4, 20), page_number_in_record=2),
        PageHeader(**base, visit_date=date(2026, 4, 20), page_number_in_record=3),
        PageHeader(**base, visit_date=date(2026, 4, 27), page_number_in_record=1),
        PageHeader(**base, visit_date=date(2026, 4, 27), page_number_in_record=2),
    ]
