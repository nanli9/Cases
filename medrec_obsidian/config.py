"""Configuration loading and defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class OcrConfig(BaseModel):
    engine: str = "pytesseract"
    languages: str = "chi_sim+eng"
    dpi: int = 300


class ObsidianConfig(BaseModel):
    root_folder: str = "Medical Records"
    patients_folder: str = "Patients"
    visits_folder: str = "Visits"
    topics_folder: str = "Topics"
    diseases_subfolder: str = "Diseases"
    symptoms_subfolder: str = "Symptoms"
    medications_subfolder: str = "Medications"
    herbs_subfolder: str = "Herbs"
    lab_indicators_subfolder: str = "Lab Indicators"
    tcm_patterns_subfolder: str = "TCM Patterns"
    relations_folder: str = "Relations"
    sources_folder: str = "Sources"
    tag_prefix: str = "medical-record"


class DedupConfig(BaseModel):
    fuzzy_threshold: int = 85
    content_hash_dedup: bool = True


class Config(BaseModel):
    ocr: OcrConfig = Field(default_factory=OcrConfig)
    obsidian: ObsidianConfig = Field(default_factory=ObsidianConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    min_chinese_char_ratio: float = 0.3
    language: str = "zh-CN"

    @classmethod
    def load(cls, path: Optional[Path] = None) -> Config:
        """Load config from YAML file, falling back to defaults."""
        if path and path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    def vault_root(self, vault_path: Path) -> Path:
        """Return the Medical Records root directory inside the vault."""
        return vault_path / self.obsidian.root_folder

    def patients_dir(self, vault_path: Path) -> Path:
        return self.vault_root(vault_path) / self.obsidian.patients_folder

    def visits_dir(self, vault_path: Path) -> Path:
        return self.vault_root(vault_path) / self.obsidian.visits_folder

    def topics_dir(self, vault_path: Path, subfolder: str) -> Path:
        return self.vault_root(vault_path) / self.obsidian.topics_folder / subfolder

    def relations_dir(self, vault_path: Path) -> Path:
        return self.vault_root(vault_path) / self.obsidian.relations_folder

    def sources_dir(self, vault_path: Path) -> Path:
        return self.vault_root(vault_path) / self.obsidian.sources_folder
