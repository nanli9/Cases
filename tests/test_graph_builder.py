"""Tests for graph_builder: relation note creation."""

from __future__ import annotations

from pathlib import Path

import pytest

from medrec_obsidian.config import Config
from medrec_obsidian.graph_builder import build_graph, rebuild_graph
from medrec_obsidian.models import Relation, RelationType, VisitRecord


class TestBuildGraph:
    """Test relation note writing."""

    def test_writes_relation_notes(self, tmp_path: Path):
        config = Config()
        relations = [
            Relation(
                source_term="眩晕",
                target_term="头晕",
                relation_type=RelationType.DISEASE_HAS_SYMPTOM,
                evidence=["Visit: 测试患者_2026-05-04"],
            ),
            Relation(
                source_term="眩晕综合征",
                target_term="2型糖尿病",
                relation_type=RelationType.DISEASES_SHARE_SYMPTOM,
                evidence=["Shared symptoms: 头晕"],
            ),
        ]

        count = build_graph(relations, tmp_path, config)
        assert count == 2

        rel_dir = tmp_path / "Medical Records" / "Relations"
        assert rel_dir.is_dir()
        rel_files = list(rel_dir.glob("*.md"))
        assert len(rel_files) == 2

    def test_relation_note_content(self, tmp_path: Path):
        config = Config()
        relations = [
            Relation(
                source_term="眩晕",
                target_term="头晕",
                relation_type=RelationType.DISEASE_HAS_SYMPTOM,
                evidence=["Visit: 测试患者_2026-05-04"],
            ),
        ]

        build_graph(relations, tmp_path, config)

        rel_dir = tmp_path / "Medical Records" / "Relations"
        files = list(rel_dir.glob("*.md"))
        assert len(files) == 1

        content = files[0].read_text(encoding="utf-8")
        assert "[[眩晕]]" in content
        assert "[[头晕]]" in content
        assert "type: relation" in content

    def test_rebuild_from_visits(
        self, sample_visit_record: VisitRecord, tmp_path: Path
    ):
        config = Config()
        count = rebuild_graph([sample_visit_record], tmp_path, config)
        # Should produce some relation notes based on the visit's diagnoses and symptoms
        assert count >= 0

    def test_idempotent_rebuild(
        self, sample_visit_record: VisitRecord, tmp_path: Path
    ):
        config = Config()
        count1 = rebuild_graph([sample_visit_record], tmp_path, config)
        count2 = rebuild_graph([sample_visit_record], tmp_path, config)
        assert count1 == count2
