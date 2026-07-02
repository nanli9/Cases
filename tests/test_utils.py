"""Tests for utility helpers."""

from __future__ import annotations

from datetime import date

import pytest

from medrec_obsidian.utils import (
    chinese_char_ratio,
    compute_content_hash,
    count_chinese_chars,
    formula_note_name,
    link_safe,
    parse_chinese_date,
    sanitize_filename,
    today_str,
    visit_note_link,
)


class TestSanitizeFilename:
    def test_strips_illegal_chars(self):
        assert sanitize_filename('a/b:c*d?"e<f>g|h') == "abcdefgh"

    def test_collapses_whitespace(self):
        assert sanitize_filename("a   b\t c") == "a b c"

    def test_empty_becomes_unnamed(self):
        assert sanitize_filename("///") == "unnamed"
        assert sanitize_filename("   ") == "unnamed"

    def test_keeps_chinese(self):
        assert sanitize_filename("桂枝汤") == "桂枝汤"


class TestLinkSafe:
    def test_replaces_slash_and_hash(self):
        out = link_safe("谷草/谷丙比值")
        assert "/" not in out
        assert out == "谷草／谷丙比值"

    def test_replaces_hash(self):
        assert link_safe("中性(NEUT#)") == "中性(NEUT＃)"

    def test_noop_on_clean_name(self):
        assert link_safe("桂枝") == "桂枝"

    def test_result_survives_sanitize(self):
        """A link-safe name must be preserved by sanitize_filename (file == link)."""
        name = link_safe("谷草/谷丙比值")
        assert sanitize_filename(name) == name


class TestLinkTargets:
    def test_visit_note_link(self):
        assert visit_note_link("张三", "2026-01-01", "caseA.pdf") == "张三/2026-01-01__caseA"

    def test_visit_note_link_sanitizes(self):
        assert visit_note_link("张/三", "2026-01-01", "a/b.pdf") == "张三/2026-01-01__b"

    def test_formula_name_with_id(self):
        assert formula_note_name("F001", "张三", "2026-01-01") == "方-F001"

    def test_formula_name_fallback(self):
        assert formula_note_name("", "张三", "2026-01-01") == "方-张三-2026-01-01"


class TestDates:
    def test_iso(self):
        assert parse_chinese_date("2026-05-04") == date(2026, 5, 4)

    def test_iso_single_digit(self):
        assert parse_chinese_date("2026-5-4") == date(2026, 5, 4)

    def test_chinese(self):
        assert parse_chinese_date("2026年5月4日") == date(2026, 5, 4)

    def test_invalid(self):
        assert parse_chinese_date("not a date") is None
        assert parse_chinese_date("") is None

    def test_today_str_format(self):
        s = today_str()
        assert parse_chinese_date(s) is not None


class TestTextHelpers:
    def test_content_hash_ignores_whitespace(self):
        assert compute_content_hash("a b c") == compute_content_hash("abc")

    def test_content_hash_differs(self):
        assert compute_content_hash("abc") != compute_content_hash("abd")

    def test_count_chinese_chars(self):
        assert count_chinese_chars("桂枝abc汤") == 3

    def test_chinese_char_ratio(self):
        assert chinese_char_ratio("桂枝") == 1.0
        assert chinese_char_ratio("") == 0.0
        assert 0 < chinese_char_ratio("桂ab") < 1


def test_fuzzy_match_optional_dep():
    """fuzzy_match uses rapidfuzz, which is now optional — skip if absent."""
    pytest.importorskip("rapidfuzz")
    from medrec_obsidian.utils import fuzzy_match

    assert fuzzy_match("桂枝汤", ["桂枝汤", "麻黄汤"]) == "桂枝汤"
    assert fuzzy_match("zzz", ["桂枝汤"], threshold=90) is None
