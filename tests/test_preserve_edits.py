"""Tests that manual edits survive vault regeneration (Feature 3)."""

from __future__ import annotations

from pathlib import Path

import yaml

from medrec_obsidian.config import Config
from medrec_obsidian.extractor import extract_keywords
from medrec_obsidian.notes import parse_existing_note, write_note_preserving
from medrec_obsidian.obsidian_writer import write_vault


def _split_frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    _, fm, _ = text.split("---\n", 2)
    return yaml.safe_load(fm)


def _build(sample_visits, tmp_path: Path) -> Path:
    config = Config()
    keywords = extract_keywords(sample_visits)
    write_vault(sample_visits, keywords, tmp_path, config)
    return tmp_path / "Medical Records"


def test_herb_reference_field_and_note_survive(sample_visits, tmp_path: Path):
    root = _build(sample_visits, tmp_path)
    herb = root / "Topics" / "Herbs" / "桂枝.md"
    text = herb.read_text(encoding="utf-8")
    # Generator emits a blank 性味 template and a generated 所属方剂 section.
    assert "性味: ''" in text
    assert "## 所属方剂" in text

    # User fills in the reference field and adds a free-text 笔记 section.
    text = text.replace("性味: ''", "性味: 辛温")
    text = text.rstrip("\n") + "\n\n## 笔记\n\n桂枝解表要药，需牢记。\n"
    herb.write_text(text, encoding="utf-8")

    # Regenerate.
    _build(sample_visits, tmp_path)
    regenerated = herb.read_text(encoding="utf-8")

    fm = _split_frontmatter(regenerated)
    assert fm["性味"] == "辛温"  # user reference value preserved
    assert "## 笔记" in regenerated
    assert "桂枝解表要药，需牢记。" in regenerated  # user note preserved verbatim
    assert "## 所属方剂" in regenerated  # generated section still refreshed


def test_herb_note_not_duplicated_on_second_regen(sample_visits, tmp_path: Path):
    root = _build(sample_visits, tmp_path)
    herb = root / "Topics" / "Herbs" / "桂枝.md"
    text = herb.read_text(encoding="utf-8").rstrip("\n")
    text += "\n\n## 笔记\n\n自定义笔记内容。\n"
    herb.write_text(text, encoding="utf-8")

    _build(sample_visits, tmp_path)
    once = herb.read_text(encoding="utf-8")
    _build(sample_visits, tmp_path)
    twice = herb.read_text(encoding="utf-8")

    assert once == twice  # idempotent with a preserved note
    assert twice.count("## 笔记") == 1
    assert twice.count("自定义笔记内容。") == 1


def test_patient_note_user_section_survives(sample_visits, tmp_path: Path):
    root = _build(sample_visits, tmp_path)
    patient = root / "Patients" / "张三.md"
    text = patient.read_text(encoding="utf-8").rstrip("\n")
    text += "\n\n## 笔记\n\n随访提醒：三个月后复查。\n"
    patient.write_text(text, encoding="utf-8")

    _build(sample_visits, tmp_path)
    regenerated = patient.read_text(encoding="utf-8")

    assert "## 笔记" in regenerated
    assert "随访提醒：三个月后复查。" in regenerated
    assert "## 就诊记录" in regenerated  # generated section still present


def test_unknown_user_frontmatter_key_preserved(tmp_path: Path):
    path = tmp_path / "note.md"
    write_note_preserving(path, {"type": "herb", "name": "桂枝"}, "桂枝", ["body"])
    # User adds an unrecognized frontmatter key.
    text = path.read_text(encoding="utf-8").replace(
        "name: 桂枝", "name: 桂枝\nmy_rating: 5"
    )
    path.write_text(text, encoding="utf-8")

    write_note_preserving(path, {"type": "herb", "name": "桂枝"}, "桂枝", ["body"])
    fm, _ = parse_existing_note(path)
    assert fm["my_rating"] == 5


def test_parse_handles_missing_and_malformed(tmp_path: Path):
    no_fm = tmp_path / "a.md"
    no_fm.write_text("# 标题\n\n正文\n", encoding="utf-8")
    fm, section = parse_existing_note(no_fm)
    assert fm == {}
    assert section is None

    missing = tmp_path / "does_not_exist.md"
    assert parse_existing_note(missing) == ({}, None)
