"""Tests for obsidian_writer: markdown generation and vault structure."""

from __future__ import annotations

from pathlib import Path

import pytest

from medrec_obsidian.config import Config
from medrec_obsidian.models import Keyword, KeywordType, VisitRecord
from medrec_obsidian.obsidian_writer import write_vault, _build_visit_note_content


class TestVisitNoteContent:
    """Test visit note markdown generation."""

    def test_frontmatter_present(self, sample_visit_record: VisitRecord):
        config = Config()
        content = _build_visit_note_content(sample_visit_record, config)
        assert content.startswith("---\n")
        assert "type: visit" in content
        assert "patient:" in content
        assert "visit_date:" in content

    def test_wikilinks_in_diagnoses(self, sample_visit_record: VisitRecord):
        config = Config()
        content = _build_visit_note_content(sample_visit_record, config)
        assert "[[眩晕]]" in content
        assert "[[气血亏虚证]]" in content
        assert "[[眩晕综合征]]" in content
        assert "[[2型糖尿病]]" in content

    def test_herb_table(self, sample_visit_record: VisitRecord):
        config = Config()
        content = _build_visit_note_content(sample_visit_record, config)
        assert "[[姜半夏]]" in content
        assert "[[桂枝]]" in content
        assert "12.00g" in content

    def test_symptom_wikilinks(self, sample_visit_record: VisitRecord):
        config = Config()
        content = _build_visit_note_content(sample_visit_record, config)
        assert "[[头晕]]" in content

    def test_raw_text_block(self, sample_visit_record: VisitRecord):
        config = Config()
        content = _build_visit_note_content(sample_visit_record, config)
        assert "```text" in content
        assert "Page 1 text" in content

    def test_chief_complaint_section(self, sample_visit_record: VisitRecord):
        config = Config()
        content = _build_visit_note_content(sample_visit_record, config)
        assert "## 主诉" in content
        assert "头晕两年" in content


class TestVaultWrite:
    """Test writing to vault directory."""

    def test_creates_directory_structure(
        self, sample_visit_record: VisitRecord, tmp_path: Path
    ):
        config = Config()
        keywords = [
            Keyword(
                term="眩晕",
                type=KeywordType.DISEASE,
                linked_patients=["测试患者"],
                linked_visits=["测试患者_2026-05-04"],
            ),
            Keyword(
                term="姜半夏",
                type=KeywordType.HERB,
                linked_patients=["测试患者"],
                linked_visits=["测试患者_2026-05-04"],
            ),
        ]

        stats = write_vault(
            [sample_visit_record], keywords, tmp_path, config
        )

        root = tmp_path / "Medical Records"
        assert (root / "Patients").is_dir()
        assert (root / "Visits").is_dir()
        assert (root / "Topics" / "Diseases").is_dir()
        assert (root / "Topics" / "Herbs").is_dir()
        assert (root / "Relations").is_dir()

    def test_creates_visit_note(
        self, sample_visit_record: VisitRecord, tmp_path: Path
    ):
        config = Config()
        write_vault([sample_visit_record], [], tmp_path, config)

        visit_dir = tmp_path / "Medical Records" / "Visits" / "测试患者"
        assert visit_dir.is_dir()
        visit_files = list(visit_dir.glob("*.md"))
        assert len(visit_files) == 1
        assert "2026-05-04" in visit_files[0].name

    def test_creates_patient_note(
        self, sample_visit_record: VisitRecord, tmp_path: Path
    ):
        config = Config()
        write_vault([sample_visit_record], [], tmp_path, config)

        patient_file = tmp_path / "Medical Records" / "Patients" / "测试患者.md"
        assert patient_file.exists()
        content = patient_file.read_text(encoding="utf-8")
        assert "type: patient" in content
        assert "测试患者" in content

    def test_creates_topic_notes(
        self, sample_visit_record: VisitRecord, tmp_path: Path
    ):
        config = Config()
        keywords = [
            Keyword(
                term="眩晕",
                type=KeywordType.DISEASE,
                linked_patients=["测试患者"],
            ),
        ]
        write_vault([sample_visit_record], keywords, tmp_path, config)

        disease_file = tmp_path / "Medical Records" / "Topics" / "Diseases" / "眩晕.md"
        assert disease_file.exists()
        content = disease_file.read_text(encoding="utf-8")
        assert "type: disease" in content

    def test_idempotent_write(
        self, sample_visit_record: VisitRecord, tmp_path: Path
    ):
        config = Config()
        write_vault([sample_visit_record], [], tmp_path, config)
        stats = write_vault([sample_visit_record], [], tmp_path, config)
        # Second write should update, not error
        assert stats["visit_notes_updated"] >= 0

    def test_stats_returned(
        self, sample_visit_record: VisitRecord, tmp_path: Path
    ):
        config = Config()
        stats = write_vault([sample_visit_record], [], tmp_path, config)
        assert "visit_notes_created" in stats
        assert "patient_notes_created" in stats
        assert stats["visit_notes_created"] == 1
        assert stats["patient_notes_created"] == 1
