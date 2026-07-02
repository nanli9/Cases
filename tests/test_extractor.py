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
