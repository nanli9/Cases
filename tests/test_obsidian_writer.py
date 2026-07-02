"""Tests for obsidian_writer: markdown generation and vault structure."""

from __future__ import annotations

from pathlib import Path

import pytest

import json

from medrec_obsidian.config import Config
from medrec_obsidian.models import Keyword, KeywordOccurrence, KeywordType, VisitRecord
from medrec_obsidian.obsidian_writer import (
    write_vault,
    _build_index,
    _build_visit_note_content,
    _merge_graph_config,
)


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
        occ = KeywordOccurrence(
            patient="测试患者",
            visit_link="测试患者/2026-05-04__test",
            visit_date="2026-05-04",
        )
        keywords = [
            Keyword(term="眩晕", type=KeywordType.DISEASE, occurrences=[occ]),
            Keyword(term="姜半夏", type=KeywordType.HERB, occurrences=[occ]),
        ]

        stats = write_vault(
            [sample_visit_record], keywords, tmp_path, config
        )

        root = tmp_path / "Medical Records"
        assert (root / "Patients").is_dir()
        assert (root / "Visits").is_dir()
        assert (root / "Topics" / "Diseases").is_dir()
        assert (root / "Topics" / "Herbs").is_dir()
        assert (root / "Formulas").is_dir()

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
                occurrences=[
                    KeywordOccurrence(
                        patient="测试患者",
                        visit_link="测试患者/2026-05-04__test",
                        visit_date="2026-05-04",
                    )
                ],
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

    def test_creates_formula_note(
        self, sample_visit_record: VisitRecord, tmp_path: Path
    ):
        config = Config()
        stats = write_vault([sample_visit_record], [], tmp_path, config)
        # sample record has formula T0001
        formula_file = tmp_path / "Medical Records" / "Formulas" / "方-T0001.md"
        assert formula_file.exists()
        assert stats["formula_notes_created"] == 1
        content = formula_file.read_text(encoding="utf-8")
        assert "type: formula" in content
        assert "[[姜半夏]]" in content

    def test_visit_links_in_topic_notes_resolve(
        self, sample_visit_record: VisitRecord, tmp_path: Path
    ):
        """Topic-note occurrence links must match a real visit-note file path."""
        from medrec_obsidian.extractor import extract_keywords

        config = Config()
        keywords = extract_keywords([sample_visit_record])
        write_vault([sample_visit_record], keywords, tmp_path, config)

        root = tmp_path / "Medical Records"
        disease = (root / "Topics" / "Diseases" / "眩晕.md").read_text(encoding="utf-8")
        # The link target used in the topic note...
        assert "测试患者/2026-05-04__test" in disease
        # ...must correspond to an actual file on disk.
        assert (root / "Visits" / "测试患者" / "2026-05-04__test.md").exists()

    def test_herb_note_is_bidirectional(
        self, sample_visit_record: VisitRecord, tmp_path: Path
    ):
        from medrec_obsidian.extractor import extract_keywords

        config = Config()
        keywords = extract_keywords([sample_visit_record])
        write_vault([sample_visit_record], keywords, tmp_path, config)

        herb = (
            tmp_path / "Medical Records" / "Topics" / "Herbs" / "姜半夏.md"
        ).read_text(encoding="utf-8")
        # Herb links back to the formula it belongs to and its co-herb.
        assert "[[方-T0001]]" in herb
        assert "[[桂枝]]" in herb


class TestBuildIndex:
    """Unit tests for the cross-link index."""

    def test_herb_maps_to_formula_and_co_herbs(self, sample_visits):
        idx = _build_index(sample_visits)
        gz = idx["herb"]["桂枝"]
        assert {"方-F001", "方-F002", "方-F003"} <= gz["formulas"]
        assert "甘草" in gz["co_herbs"]
        assert "桂枝" not in gz["co_herbs"]  # never lists itself

    def test_pattern_aggregates_symptoms_and_formulas(self, sample_visits):
        idx = _build_index(sample_visits)
        p = idx["pattern"]["风寒证"]
        assert "头痛" in p["symptoms"]
        assert "方-F001" in p["formulas"]

    def test_formula_records_diagnoses(self, sample_visits):
        idx = _build_index(sample_visits)
        f = idx["formulas"]["方-F001"]
        assert f["patient"] == "张三"
        assert "风寒证" in f["tcm"]
        assert ("桂枝", "9.00g") in f["herbs"]


class TestGraphConfig:
    def test_merge_creates_color_groups(self, tmp_path):
        config = Config()
        (tmp_path / "Medical Records" / ".obsidian").mkdir(parents=True)
        _merge_graph_config(tmp_path, config)
        gj = json.loads(
            (tmp_path / "Medical Records" / ".obsidian" / "graph.json").read_text(encoding="utf-8")
        )
        queries = {g["query"] for g in gj["colorGroups"]}
        assert "tag:#medical-record/herb" in queries
        assert "tag:#medical-record/formula" in queries

    def test_merge_preserves_existing_keys(self, tmp_path):
        config = Config()
        obs = tmp_path / "Medical Records" / ".obsidian"
        obs.mkdir(parents=True)
        (obs / "graph.json").write_text(
            json.dumps({"scale": 1.5, "colorGroups": [{"query": "tag:#custom", "color": {"a": 1, "rgb": 1}}]}),
            encoding="utf-8",
        )
        _merge_graph_config(tmp_path, config)
        gj = json.loads((obs / "graph.json").read_text(encoding="utf-8"))
        assert gj["scale"] == 1.5  # user key preserved
        assert any(g["query"] == "tag:#custom" for g in gj["colorGroups"])  # user group kept
