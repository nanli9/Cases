"""Configuration loading and defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class RenderConfig(BaseModel):
    dpi: int = 200


class ObsidianConfig(BaseModel):
    root_folder: str = "Medical Records"
    patients_folder: str = "Patients"
    doctors_folder: str = "Doctors"
    visits_folder: str = "Visits"
    topics_folder: str = "Topics"
    diseases_subfolder: str = "Diseases"
    symptoms_subfolder: str = "Symptoms"
    medications_subfolder: str = "Medications"
    herbs_subfolder: str = "Herbs"
    lab_indicators_subfolder: str = "Lab Indicators"
    tcm_patterns_subfolder: str = "TCM Patterns"
    formulas_folder: str = "Formulas"
    maps_folder: str = "Maps"
    sources_folder: str = "Sources"
    tag_prefix: str = "medical-record"


class DedupConfig(BaseModel):
    fuzzy_threshold: int = 85
    content_hash_dedup: bool = True


class Config(BaseModel):
    render: RenderConfig = Field(default_factory=RenderConfig)
    obsidian: ObsidianConfig = Field(default_factory=ObsidianConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)

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

    def doctors_dir(self, vault_path: Path) -> Path:
        return self.vault_root(vault_path) / self.obsidian.doctors_folder

    def visits_dir(self, vault_path: Path) -> Path:
        return self.vault_root(vault_path) / self.obsidian.visits_folder

    def topics_dir(self, vault_path: Path, subfolder: str) -> Path:
        return self.vault_root(vault_path) / self.obsidian.topics_folder / subfolder

    def formulas_dir(self, vault_path: Path) -> Path:
        return self.vault_root(vault_path) / self.obsidian.formulas_folder

    def maps_dir(self, vault_path: Path) -> Path:
        return self.vault_root(vault_path) / self.obsidian.maps_folder

    def sources_dir(self, vault_path: Path) -> Path:
        return self.vault_root(vault_path) / self.obsidian.sources_folder

    def records_store_path(self, vault_path: Path) -> Path:
        """Return the path to the cumulative VisitRecord store (records.json)."""
        return self.sources_dir(vault_path) / "records.json"
