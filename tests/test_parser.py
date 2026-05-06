"""Tests for parser: page grouping, deduplication, section splitting."""

from __future__ import annotations

from datetime import date

import pytest

from medrec_obsidian.config import Config
from medrec_obsidian.models import PageHeader, PageText, Sex
from medrec_obsidian.parser import group_pages, parse_visit, split_sections


class TestPageGrouping:
    """Test page grouping and deduplication."""

    def test_single_patient_grouped(
        self, sample_page_text_1: PageText, sample_page_text_2: PageText
    ):
        config = Config()
        groups = group_pages([sample_page_text_1, sample_page_text_2], config)
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_duplicate_pages_removed(
        self,
        sample_page_text_1: PageText,
        sample_page_text_duplicate: PageText,
    ):
        config = Config()
        groups = group_pages([sample_page_text_1, sample_page_text_duplicate], config)
        assert len(groups) == 1
        assert len(groups[0]) == 1  # duplicate removed

    def test_multi_visit_split(self, multi_visit_headers: list[PageHeader]):
        """Same patient with different visit dates should be split into separate groups."""
        config = Config()
        pages = [
            PageText(
                pdf_page_index=i,
                header=h,
                body_text=f"Content for page {i}",
            )
            for i, h in enumerate(multi_visit_headers)
        ]
        groups = group_pages(pages, config)
        assert len(groups) == 2
        assert len(groups[0]) == 3  # first visit: 3 pages
        assert len(groups[1]) == 2  # second visit: 2 pages

    def test_different_patients_split(self):
        config = Config()
        header_a = PageHeader(
            patient_name="患者A",
            sex=Sex.FEMALE,
            age=30,
            visit_date=date(2026, 5, 4),
            department="内科",
            registration_number="1001",
            doctor_name="医生",
        )
        header_b = PageHeader(
            patient_name="患者B",
            sex=Sex.MALE,
            age=50,
            visit_date=date(2026, 5, 4),
            department="内科",
            registration_number="1002",
            doctor_name="医生",
        )
        pages = [
            PageText(pdf_page_index=0, header=header_a, body_text="A content"),
            PageText(pdf_page_index=1, header=header_a, body_text="A page 2"),
            PageText(pdf_page_index=2, header=header_b, body_text="B content"),
        ]
        groups = group_pages(pages, config)
        assert len(groups) == 2

    def test_empty_pages(self):
        config = Config()
        groups = group_pages([], config)
        assert groups == []


class TestSectionSplitting:
    """Test section splitting from concatenated text."""

    def test_basic_sections(self):
        text = (
            "*主 诉:头晕两年\n"
            "*现 病 史:头晕，伴恶心\n"
            "*既 往 史:慢性病史：糖尿病\n"
            "*过 敏 史:否认\n"
            "初步诊断:中医诊断：\n1.眩晕\n"
        )
        sections = split_sections(text)
        assert "chief_complaint" in sections
        assert "头晕两年" in sections["chief_complaint"]
        assert "present_illness" in sections
        assert "头晕" in sections["present_illness"]
        assert "past_history" in sections
        assert "allergy_history" in sections
        assert "diagnosis" in sections

    def test_full_width_colon(self):
        text = "*主 诉：头痛三天\n*过 敏 史：否认\n"
        sections = split_sections(text)
        assert "chief_complaint" in sections
        assert "头痛三天" in sections["chief_complaint"]

    def test_treatment_section(self):
        text = (
            "处 置:检查：\n"
            "1.生化（22）  360\n"
            "草药方 43622340 贴数：7\n"
            "姜半夏12.00g  桂枝12.00g\n"
            "注意事项:嘱患者按医嘱用药\n"
        )
        sections = split_sections(text)
        assert "treatment_plan" in sections
        assert "notes" in sections
        assert "草药方" in sections["treatment_plan"]
        assert "嘱患者" in sections["notes"]


class TestParseVisit:
    """Test full visit parsing from page groups."""

    def test_basic_parse(
        self, sample_page_text_1: PageText, sample_page_text_2: PageText
    ):
        visit = parse_visit(
            [sample_page_text_1, sample_page_text_2], "test.pdf"
        )
        assert visit.patient_name == "测试患者"
        assert visit.visit_date == date(2026, 5, 4)
        assert visit.source_pdf == "test.pdf"
        assert len(visit.source_pages) == 2
        assert "头晕" in visit.chief_complaint

    def test_raw_text_by_page(
        self, sample_page_text_1: PageText, sample_page_text_2: PageText
    ):
        visit = parse_visit(
            [sample_page_text_1, sample_page_text_2], "test.pdf"
        )
        assert 0 in visit.raw_text_by_page
        assert 1 in visit.raw_text_by_page
