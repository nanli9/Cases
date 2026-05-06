"""Tests for extractor: diagnosis parsing, herb extraction, lab parsing, symptom matching."""

from __future__ import annotations

import pytest

from medrec_obsidian.extractor import (
    _extract_herbal_formulas,
    _parse_herbs,
    _parse_lab_text,
    _parse_numbered_diagnoses,
    _parse_diagnosis_qualifier,
    extract_all,
    extract_keywords,
    extract_relations,
)
from medrec_obsidian.models import KeywordType, RelationType, VisitRecord


class TestDiagnosisParsing:
    """Test numbered diagnosis item parsing."""

    def test_basic_diagnoses(self):
        text = "1.眩晕  2.气血亏虚证"
        diags = _parse_numbered_diagnoses(text)
        assert len(diags) == 2
        assert diags[0].name == "眩晕"
        assert diags[0].index == 1
        assert diags[1].name == "气血亏虚证"

    def test_pipe_qualifier(self):
        text = "1.单纯手震颤|特发性震颤  2.睡眠障碍"
        diags = _parse_numbered_diagnoses(text)
        assert len(diags) == 2
        assert diags[0].name == "单纯手震颤"
        assert diags[0].qualifier == "特发性震颤"

    def test_bracket_qualifier(self):
        text = "1.偏头痛不伴有先兆[普通偏头痛]"
        diags = _parse_numbered_diagnoses(text)
        assert len(diags) == 1
        assert diags[0].name == "偏头痛不伴有先兆"
        assert diags[0].qualifier == "普通偏头痛"

    def test_grade_qualifier(self):
        text = "1.高血压1级|极高危组"
        diags = _parse_numbered_diagnoses(text)
        assert len(diags) == 1
        assert diags[0].name == "高血压1级"
        assert diags[0].qualifier == "极高危组"

    def test_stage_qualifier(self):
        text = "2.脑梗死|恢复期"
        diags = _parse_numbered_diagnoses(text)
        assert len(diags) == 1
        assert diags[0].name == "脑梗死"
        assert diags[0].qualifier == "恢复期"

    def test_many_diagnoses(self):
        text = (
            "1.颈内动脉粥样硬化  2.脑梗死|恢复期  "
            "3.尿潴留|留置导尿管  4.泌尿道感染  "
            "5.前列腺增生  6.慢性肾功能不全  7.尿酸性肾病"
        )
        diags = _parse_numbered_diagnoses(text)
        assert len(diags) == 7
        assert diags[2].name == "尿潴留"
        assert diags[2].qualifier == "留置导尿管"


class TestDiagnosisQualifier:
    def test_no_qualifier(self):
        name, qual = _parse_diagnosis_qualifier("眩晕")
        assert name == "眩晕"
        assert qual is None

    def test_pipe(self):
        name, qual = _parse_diagnosis_qualifier("脑梗死|恢复期")
        assert name == "脑梗死"
        assert qual == "恢复期"

    def test_bracket(self):
        name, qual = _parse_diagnosis_qualifier("偏头痛[普通偏头痛]")
        assert name == "偏头痛"
        assert qual == "普通偏头痛"


class TestHerbParsing:
    """Test herbal formula and individual herb parsing."""

    def test_basic_herbs(self):
        text = "姜半夏12.00g  桂枝12.00g  茯苓30.00g  麸炒白术15.00g"
        herbs = _parse_herbs(text)
        assert len(herbs) == 4
        assert herbs[0].name == "姜半夏"
        assert herbs[0].dosage_value == 12.0
        assert herbs[0].dosage_unit == "g"
        assert herbs[2].name == "茯苓"
        assert herbs[2].dosage_value == 30.0

    def test_non_gram_unit(self):
        text = "蜈蚣2.00条  全蝎5.00g"
        herbs = _parse_herbs(text)
        assert len(herbs) == 2
        assert herbs[0].name == "蜈蚣"
        assert herbs[0].dosage_unit == "条"
        assert herbs[0].dosage_value == 2.0

    def test_formula_extraction(self):
        text = (
            "草药方 43622340 贴数：7\n"
            "姜半夏12.00g  桂枝12.00g  茯苓30.00g\n"
            "黄芩片15.00g  黄芪45.00g\n"
        )
        formulas = _extract_herbal_formulas(text)
        assert len(formulas) == 1
        assert formulas[0].formula_id == "43622340"
        assert formulas[0].dose_count == 7
        assert len(formulas[0].herbs) == 5

    def test_two_formulas(self):
        text = (
            "草药方 11111111 贴数：7\n"
            "姜半夏12.00g  桂枝12.00g\n"
            "中成药处方\n"
            "天丹通络片\n"
        )
        formulas = _extract_herbal_formulas(text)
        assert len(formulas) == 1
        assert formulas[0].formula_id == "11111111"


class TestLabParsing:
    """Test laboratory result parsing."""

    def test_structured_lab_result(self):
        text = "★白细胞计数(WBC)13.05 *10^9/L ↑"
        results = _parse_lab_text(text)
        assert len(results) >= 1
        wbc = next((r for r in results if r.abbreviation == "WBC"), None)
        assert wbc is not None
        assert wbc.chinese_name == "白细胞计数"
        assert wbc.value == "13.05"
        assert wbc.is_starred

    def test_abbreviation_colon_format(self):
        text = "LDL-C: 2.04"
        results = _parse_lab_text(text)
        assert any(r.abbreviation == "LDL-C" and r.value == "2.04" for r in results)

    def test_mixed_labs(self):
        text = (
            "★ 尿酸(UA)456.3 μmol/L ↑；"
            "★ 尿素(Urea)11.88 mmol/L ↑；"
            "★ 肌酐(Crea)134.7 μmol/L ↑"
        )
        results = _parse_lab_text(text)
        assert len(results) >= 3


class TestSymptomExtraction:
    """Test symptom dictionary matching."""

    def test_symptoms_in_chief_complaint(self, sample_visit_record: VisitRecord):
        from medrec_obsidian.extractor import _extract_symptoms

        visit = sample_visit_record
        visit.chief_complaint = "头晕两年，加重2月"
        visit.present_illness = "头晕，每次持续几分钟，伴恶心。胸闷胸痛。口干。"
        _extract_symptoms(visit)
        assert "头晕" in visit.symptoms
        assert "恶心" in visit.symptoms
        assert "胸闷" in visit.symptoms
        assert "口干" in visit.symptoms


class TestExtractKeywords:
    """Test keyword extraction from visits."""

    def test_keyword_types(self, sample_visit_record: VisitRecord):
        keywords = extract_keywords([sample_visit_record])
        types = {kw.type for kw in keywords}
        # Should have at least diseases and herbs
        assert KeywordType.HERB in types


class TestExtractRelations:
    """Test relation extraction from visits."""

    def test_disease_has_symptom(self, sample_visit_record: VisitRecord):
        relations = extract_relations([sample_visit_record])
        dhs = [r for r in relations if r.relation_type == RelationType.DISEASE_HAS_SYMPTOM]
        assert len(dhs) > 0

    def test_patient_has_disease(self, sample_visit_record: VisitRecord):
        relations = extract_relations([sample_visit_record])
        phd = [r for r in relations if r.relation_type == RelationType.PATIENT_HAS_DISEASE]
        assert len(phd) > 0
        assert any(r.source_term == "测试患者" for r in phd)
