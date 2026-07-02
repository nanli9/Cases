"""Tests for extractor: keyword extraction from VisitRecords."""

from __future__ import annotations

import pytest

from medrec_obsidian.extractor import extract_keywords
from medrec_obsidian.models import KeywordType, VisitRecord


class TestExtractKeywords:
    """Test keyword extraction from visits."""

    def test_keyword_types(self, sample_visit_record: VisitRecord):
        keywords = extract_keywords([sample_visit_record])
        types = {kw.type for kw in keywords}
        # Should have at least diseases and herbs
        assert KeywordType.HERB in types

    def test_disease_keywords(self, sample_visit_record: VisitRecord):
        keywords = extract_keywords([sample_visit_record])
        terms = {kw.term for kw in keywords}
        assert "眩晕" in terms

    def test_links_back_to_patient(self, sample_visit_record: VisitRecord):
        keywords = extract_keywords([sample_visit_record])
        for kw in keywords:
            assert kw.occurrences
            assert all(o.patient == "测试患者" for o in kw.occurrences)

    def test_occurrence_visit_link_resolves(self, sample_visit_record: VisitRecord):
        # The occurrence link must point at the real visit-note path, not 患者_日期.
        keywords = extract_keywords([sample_visit_record])
        kw = next(k for k in keywords if k.term == "眩晕")
        assert kw.occurrences[0].visit_link == "测试患者/2026-05-04__test"

    def test_herb_occurrence_records_dosage(self, sample_visit_record: VisitRecord):
        keywords = extract_keywords([sample_visit_record])
        herb = next(k for k in keywords if k.term == "姜半夏")
        assert herb.occurrences[0].detail == "12.00g"

    def test_pattern_vs_disease_typing(self, sample_visits):
        keywords = {k.term: k for k in extract_keywords(sample_visits)}
        assert keywords["风寒证"].type == KeywordType.TCM_PATTERN  # ends in 证
        assert keywords["感冒"].type == KeywordType.DISEASE
        assert keywords["上呼吸道感染"].type == KeywordType.DISEASE

    def test_multi_visit_occurrence_count(self, sample_visits):
        keywords = {k.term: k for k in extract_keywords(sample_visits)}
        # 桂枝 appears in all three visits (F001, F002, F003).
        distinct = {o.visit_link for o in keywords["桂枝"].occurrences}
        assert len(distinct) == 3

    def test_lab_term_is_link_safe(self, sample_visits):
        terms = {k.term for k in extract_keywords(sample_visits)}
        # '/' and '#' normalized to full-width so filename == wikilink.
        assert "谷草／谷丙比值" in terms
        assert "中性粒细胞绝对值(NEUT＃)" in terms
        assert not any("/" in t or "#" in t for t in terms)
