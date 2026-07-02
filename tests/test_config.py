"""Tests for configuration loading and path helpers."""

from __future__ import annotations

from pathlib import Path

from medrec_obsidian.config import Config


def test_defaults():
    cfg = Config()
    assert cfg.obsidian.root_folder == "Medical Records"
    assert cfg.render.dpi == 200
    assert cfg.obsidian.formulas_folder == "Formulas"
    assert cfg.obsidian.doctors_folder == "Doctors"


def test_load_none_returns_defaults():
    assert Config.load(None).obsidian.root_folder == "Medical Records"


def test_load_from_yaml(tmp_path: Path):
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text(
        "render:\n  dpi: 300\nobsidian:\n  root_folder: My Records\n",
        encoding="utf-8",
    )
    cfg = Config.load(cfg_file)
    assert cfg.render.dpi == 300
    assert cfg.obsidian.root_folder == "My Records"


def test_dir_helpers(tmp_path: Path):
    cfg = Config()
    vault = tmp_path
    root = cfg.vault_root(vault)
    assert root == vault / "Medical Records"
    assert cfg.patients_dir(vault) == root / "Patients"
    assert cfg.doctors_dir(vault) == root / "Doctors"
    assert cfg.visits_dir(vault) == root / "Visits"
    assert cfg.formulas_dir(vault) == root / "Formulas"
    assert cfg.maps_dir(vault) == root / "Maps"
    assert cfg.sources_dir(vault) == root / "Sources"
    assert cfg.topics_dir(vault, "Herbs") == root / "Topics" / "Herbs"
