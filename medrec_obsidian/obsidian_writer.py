"""Obsidian vault writer: creates and updates markdown notes with YAML frontmatter."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

from .config import Config
from .models import (
    Keyword,
    KeywordType,
    ProcessingManifest,
    VisitRecord,
)
from .utils import sanitize_filename, today_str

logger = logging.getLogger(__name__)


def write_vault(
    visits: list[VisitRecord],
    keywords: list["Keyword"],
    vault_path: Path,
    config: Config,
    source_pdf_path: Optional[Path] = None,
    manifest: Optional[ProcessingManifest] = None,
) -> dict[str, int]:
    """Write all visit records and keywords to the Obsidian vault.

    Returns a summary dict with counts of files created/updated.
    """
    stats: dict[str, int] = {
        "visit_notes_created": 0,
        "visit_notes_updated": 0,
        "patient_notes_created": 0,
        "patient_notes_updated": 0,
        "topic_notes_created": 0,
        "topic_notes_updated": 0,
    }

    # Ensure directory structure
    _ensure_vault_dirs(vault_path, config)

    # Write visit notes
    for visit in visits:
        created = _write_visit_note(visit, vault_path, config)
        if created:
            stats["visit_notes_created"] += 1
        else:
            stats["visit_notes_updated"] += 1

    # Write patient notes (aggregate across visits)
    patients = _group_visits_by_patient(visits)
    for patient_name, patient_visits in patients.items():
        created = _write_patient_note(patient_name, patient_visits, vault_path, config)
        if created:
            stats["patient_notes_created"] += 1
        else:
            stats["patient_notes_updated"] += 1

    # Write topic notes for keywords
    for kw in keywords:
        created = _write_topic_note(kw, vault_path, config)
        if created:
            stats["topic_notes_created"] += 1
        else:
            stats["topic_notes_updated"] += 1

    # Write sources
    if source_pdf_path and source_pdf_path.exists():
        _write_sources(visits, source_pdf_path, vault_path, config, manifest)

    return stats


def _ensure_vault_dirs(vault_path: Path, config: Config) -> None:
    """Create the vault directory structure."""
    obs = config.obsidian
    root = config.vault_root(vault_path)

    dirs = [
        root / obs.patients_folder,
        root / obs.visits_folder,
        root / obs.topics_folder / obs.diseases_subfolder,
        root / obs.topics_folder / obs.symptoms_subfolder,
        root / obs.topics_folder / obs.medications_subfolder,
        root / obs.topics_folder / obs.herbs_subfolder,
        root / obs.topics_folder / obs.lab_indicators_subfolder,
        root / obs.topics_folder / obs.tcm_patterns_subfolder,
        root / obs.relations_folder,
        root / obs.sources_folder / "manifests",
        root / obs.sources_folder / "ocr",
        root / obs.sources_folder / "pdfs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def _write_visit_note(
    visit: VisitRecord, vault_path: Path, config: Config
) -> bool:
    """Write a per-visit note. Returns True if newly created, False if updated."""
    obs = config.obsidian
    root = config.vault_root(vault_path)

    # Create patient subdirectory under Visits
    patient_dir = root / obs.visits_folder / sanitize_filename(visit.patient_name)
    patient_dir.mkdir(parents=True, exist_ok=True)

    pdf_stem = Path(visit.source_pdf).stem if visit.source_pdf else "unknown"
    filename = f"{visit.visit_date.isoformat()}__{sanitize_filename(pdf_stem)}.md"
    filepath = patient_dir / filename
    is_new = not filepath.exists()

    # Build the note content
    content = _build_visit_note_content(visit, config)
    filepath.write_text(content, encoding="utf-8")

    return is_new


def _build_visit_note_content(visit: VisitRecord, config: Config) -> str:
    """Build the full markdown content for a visit note."""
    tag_prefix = config.obsidian.tag_prefix
    lines: list[str] = []

    # YAML frontmatter
    frontmatter = {
        "type": "visit",
        "patient": f"[[{visit.patient_name}]]",
        "sex": visit.sex.value,
        "age": visit.age,
        "visit_date": visit.visit_date.isoformat(),
        "department": visit.department,
        "registration_number": visit.registration_number,
        "fee_category": visit.fee_category,
        "doctor": f"[[{visit.doctor}]]" if visit.doctor else "",
        "tcm_diagnoses": [f"[[{d.name}]]" for d in visit.tcm_diagnoses],
        "western_diagnoses": [f"[[{d.name}]]" for d in visit.western_diagnoses],
        "source_pdf": visit.source_pdf,
        "source_pages": visit.source_pages,
        "extraction_confidence": visit.extraction_confidence,
        "tags": [
            f"{tag_prefix}/visit",
            f"{tag_prefix}/{visit.visit_date.strftime('%Y-%m')}",
        ],
        "created": today_str(),
    }
    if visit.document_id:
        frontmatter["document_id"] = visit.document_id

    lines.append("---")
    lines.append(yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False).strip())
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# {visit.patient_name} -- {visit.visit_date.isoformat()} 就诊记录")
    lines.append("")

    # Metadata line
    meta_parts = [f"**门诊号**: {visit.registration_number}"]
    if visit.department:
        meta_parts.append(f"**科室**: {visit.department}")
    if visit.fee_category:
        meta_parts.append(f"**费别**: {visit.fee_category}")
    lines.append(" | ".join(meta_parts))
    if visit.doctor:
        lines.append(f"**医生**: [[{visit.doctor}]]")
    lines.append("")

    # Chief complaint
    if visit.chief_complaint:
        lines.append("## 主诉")
        lines.append(visit.chief_complaint)
        lines.append("")

    # Present illness
    if visit.present_illness:
        lines.append("## 现病史")
        lines.append(visit.present_illness)
        lines.append("")

    # Follow-ups
    if visit.follow_ups:
        for fu in visit.follow_ups:
            lines.append(f"### {fu.date_str} 复诊")
            lines.append(fu.text)
            if fu.lab_results:
                lines.append("")
                lines.append("**检查结果:**")
                lines.append("")
                lines.append("| 指标 | 缩写 | 值 | 单位 | 趋势 |")
                lines.append("|------|------|----|------|------|")
                for lab in fu.lab_results:
                    direction = lab.direction or ""
                    star = " ★" if lab.is_starred else ""
                    lines.append(
                        f"| {lab.chinese_name}{star} | {lab.abbreviation} | {lab.value} | {lab.unit} | {direction} |"
                    )
            lines.append("")

    # Past history
    has_past = visit.chronic_history or visit.infectious_history or visit.surgical_history
    if has_past:
        lines.append("## 既往史")
        if visit.chronic_history:
            lines.append(f"- **慢性病史**: {visit.chronic_history}")
        if visit.infectious_history:
            lines.append(f"- **传染病史**: {visit.infectious_history}")
        if visit.surgical_history:
            lines.append(f"- **手术/外伤史**: {visit.surgical_history}")
        lines.append("")

    # Allergy
    if visit.allergy_history:
        lines.append("## 过敏史")
        lines.append(visit.allergy_history)
        lines.append("")

    # Personal history
    if visit.personal_history:
        lines.append("## 个人史")
        lines.append(visit.personal_history)
        lines.append("")

    # Family history
    if visit.family_history:
        lines.append("## 家族史")
        lines.append(visit.family_history)
        lines.append("")

    # Vital signs
    if visit.vital_signs_bp:
        lines.append("## 生命体征")
        lines.append(f"BP: {visit.vital_signs_bp} mmHg")
        lines.append("")

    # Physical exam
    if visit.physical_exam:
        lines.append("## 体格检查")
        lines.append(visit.physical_exam)
        lines.append("")

    # TCM four exams
    if visit.tcm_tongue or visit.tcm_pulse:
        lines.append("## 中医四诊")
        if visit.tcm_tongue:
            lines.append(f"- **舌象**: {visit.tcm_tongue}")
        if visit.tcm_pulse:
            lines.append(f"- **脉象**: {visit.tcm_pulse}")
        lines.append("")

    # Pattern basis
    if visit.pattern_basis:
        lines.append("## 辨证依据")
        lines.append(visit.pattern_basis)
        lines.append("")

    # Treatment principle
    if visit.treatment_principle:
        lines.append("## 治则治法")
        lines.append(visit.treatment_principle)
        lines.append("")

    # Diagnoses
    if visit.tcm_diagnoses or visit.western_diagnoses:
        lines.append("## 初步诊断")
        lines.append("")
        if visit.tcm_diagnoses:
            lines.append("### 中医诊断")
            for d in visit.tcm_diagnoses:
                qual = f" ({d.qualifier})" if d.qualifier else ""
                lines.append(f"{d.index}. [[{d.name}]]{qual}")
            lines.append("")
        if visit.western_diagnoses:
            lines.append("### 西医诊断")
            for d in visit.western_diagnoses:
                qual = f" ({d.qualifier})" if d.qualifier else ""
                lines.append(f"{d.index}. [[{d.name}]]{qual}")
            lines.append("")

    # Treatment plan
    has_treatment = (
        visit.exam_orders
        or visit.medications
        or visit.chinese_patent_medicines
        or visit.herbal_formulas
    )
    if has_treatment:
        lines.append("## 处置")
        lines.append("")

        # Exam orders
        if visit.exam_orders:
            lines.append("### 检查")
            lines.append("")
            lines.append("| 项目 | 费用 |")
            lines.append("|------|------|")
            for order in visit.exam_orders:
                cost = f"{order.cost:.0f}" if order.cost else ""
                lines.append(f"| {order.name} | {cost} |")
            lines.append("")

        # Western medications
        if visit.medications:
            lines.append("### 西药处方")
            for med in visit.medications:
                spec = f"({med.specification})" if med.specification else ""
                lines.append(
                    f"- [[{med.name}]]{spec} {med.quantity} {med.frequency} {med.single_dose} {med.route}"
                )
            lines.append("")

        # Chinese patent medicines
        if visit.chinese_patent_medicines:
            lines.append("### 中成药处方")
            for med in visit.chinese_patent_medicines:
                spec = f"({med.specification})" if med.specification else ""
                lines.append(
                    f"- [[{med.name}]]{spec} {med.quantity} {med.frequency} {med.single_dose} {med.route}"
                )
            lines.append("")

        # Herbal formulas
        if visit.herbal_formulas:
            lines.append("### 草药方")
            for formula in visit.herbal_formulas:
                lines.append(
                    f"> **方号**: {formula.formula_id} | **贴数**: {formula.dose_count}"
                )
                lines.append("")
                lines.append("| 药物 | 剂量 |")
                lines.append("|------|------|")
                for herb in formula.herbs:
                    lines.append(f"| [[{herb.name}]] | {herb.dosage} |")
                lines.append("")

    # Symptoms
    if visit.symptoms:
        lines.append("## 症状")
        for s in visit.symptoms:
            lines.append(f"- [[{s}]]")
        lines.append("")

    # Notes
    if visit.notes:
        lines.append("## 注意事项")
        lines.append(visit.notes)
        lines.append("")

    # Warnings
    if visit.warnings:
        lines.append("## 提取警告")
        for w in visit.warnings:
            lines.append(f"- {w}")
        lines.append("")

    # Raw extracted text
    if visit.raw_text_by_page:
        lines.append("## 原始提取文本")
        lines.append("")
        lines.append("```text")
        for page_idx in sorted(visit.raw_text_by_page.keys()):
            lines.append(f"--- Page {page_idx + 1} ---")
            lines.append(visit.raw_text_by_page[page_idx])
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _write_patient_note(
    patient_name: str,
    visits: list[VisitRecord],
    vault_path: Path,
    config: Config,
) -> bool:
    """Write or update a patient profile note. Returns True if newly created."""
    obs = config.obsidian
    root = config.vault_root(vault_path)
    tag_prefix = obs.tag_prefix

    filepath = root / obs.patients_folder / f"{sanitize_filename(patient_name)}.md"
    is_new = not filepath.exists()

    # Aggregate data from all visits
    first = visits[0]
    all_tcm_diags: list[str] = []
    all_western_diags: list[str] = []
    all_symptoms: list[str] = []
    all_medications: list[str] = []
    all_herbs: list[str] = []
    reg_numbers: list[str] = []

    for v in visits:
        for d in v.tcm_diagnoses:
            if d.name not in all_tcm_diags:
                all_tcm_diags.append(d.name)
        for d in v.western_diagnoses:
            if d.name not in all_western_diags:
                all_western_diags.append(d.name)
        for s in v.symptoms:
            if s not in all_symptoms:
                all_symptoms.append(s)
        for m in v.medications:
            if m.name not in all_medications:
                all_medications.append(m.name)
        for m in v.chinese_patent_medicines:
            if m.name not in all_medications:
                all_medications.append(m.name)
        for h in v.herbs:
            if h not in all_herbs:
                all_herbs.append(h)
        if v.registration_number and v.registration_number not in reg_numbers:
            reg_numbers.append(v.registration_number)

    # Build content
    lines: list[str] = []

    frontmatter = {
        "type": "patient",
        "name": patient_name,
        "sex": first.sex.value,
        "age": first.age,
        "aliases": [],
        "created": today_str(),
        "updated": today_str(),
        "source_count": len(visits),
        "tags": [f"{tag_prefix}/patient"],
    }

    lines.append("---")
    lines.append(yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False).strip())
    lines.append("---")
    lines.append("")
    lines.append(f"# {patient_name}")
    lines.append("")

    # Identity
    lines.append(f"**性别**: {first.sex.value} | **门诊号**: {', '.join(reg_numbers)}")
    lines.append("")

    # Current keyword summary
    lines.append("## Current keyword summary")
    lines.append("")

    if all_western_diags or all_tcm_diags:
        lines.append("Diseases:")
        for d in all_western_diags + all_tcm_diags:
            lines.append(f"- [[{d}]]")
        lines.append("")

    if all_symptoms:
        lines.append("Symptoms:")
        for s in all_symptoms:
            lines.append(f"- [[{s}]]")
        lines.append("")

    if all_medications:
        lines.append("Medications:")
        for m in all_medications:
            lines.append(f"- [[{m}]]")
        lines.append("")

    if all_herbs:
        lines.append("Herbs:")
        for h in all_herbs:
            lines.append(f"- [[{h}]]")
        lines.append("")

    # Visits
    lines.append("## Visits")
    lines.append("")
    for v in sorted(visits, key=lambda x: x.visit_date, reverse=True):
        pdf_stem = Path(v.source_pdf).stem if v.source_pdf else "unknown"
        visit_link = f"{v.patient_name}/{v.visit_date.isoformat()}__{sanitize_filename(pdf_stem)}"
        diags = ", ".join(d.name for d in v.tcm_diagnoses + v.western_diagnoses)
        lines.append(
            f"### {v.visit_date.isoformat()} -- {v.hospital}"
        )
        lines.append("")
        lines.append(f"Source: [[{visit_link}]]")
        lines.append(f"Pages: {_format_page_range(v.source_pages)}")
        lines.append(f"Extraction confidence: {_confidence_label(v.extraction_confidence)}")
        lines.append("")
        if v.chief_complaint:
            lines.append(f"#### Chief complaint")
            lines.append(v.chief_complaint)
            lines.append("")
        if diags:
            lines.append(f"#### Diagnoses")
            if v.tcm_diagnoses:
                lines.append("TCM:")
                for d in v.tcm_diagnoses:
                    lines.append(f"- [[{d.name}]]")
            if v.western_diagnoses:
                lines.append("Western:")
                for d in v.western_diagnoses:
                    lines.append(f"- [[{d.name}]]")
            lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return is_new


def _write_topic_note(
    keyword: Keyword, vault_path: Path, config: Config
) -> bool:
    """Write or update a topic note for a keyword. Returns True if newly created."""
    obs = config.obsidian
    root = config.vault_root(vault_path)
    tag_prefix = obs.tag_prefix

    # Determine subfolder based on keyword type
    type_to_folder = {
        KeywordType.DISEASE: obs.diseases_subfolder,
        KeywordType.SYMPTOM: obs.symptoms_subfolder,
        KeywordType.MEDICATION: obs.medications_subfolder,
        KeywordType.HERB: obs.herbs_subfolder,
        KeywordType.LAB_INDICATOR: obs.lab_indicators_subfolder,
        KeywordType.TCM_PATTERN: obs.tcm_patterns_subfolder,
        KeywordType.IMAGING: obs.diseases_subfolder,
        KeywordType.PROCEDURE: obs.diseases_subfolder,
        KeywordType.OTHER: obs.diseases_subfolder,
    }

    subfolder = type_to_folder.get(keyword.type, obs.diseases_subfolder)
    topic_dir = root / obs.topics_folder / subfolder
    topic_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{sanitize_filename(keyword.term)}.md"
    filepath = topic_dir / filename
    is_new = not filepath.exists()

    # Build content
    lines: list[str] = []

    frontmatter = {
        "type": keyword.type.value,
        "name": keyword.term,
        "aliases": keyword.aliases,
        "tags": [f"{tag_prefix}/{keyword.type.value}"],
    }

    lines.append("---")
    lines.append(yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False).strip())
    lines.append("---")
    lines.append("")
    lines.append(f"# {keyword.term}")
    lines.append("")

    # Usage records
    if keyword.linked_patients:
        lines.append("## 相关患者")
        lines.append("")
        lines.append("| 患者 | 就诊记录 |")
        lines.append("|------|----------|")
        for i, patient in enumerate(keyword.linked_patients):
            visit_label = keyword.linked_visits[i] if i < len(keyword.linked_visits) else ""
            lines.append(f"| [[{patient}]] | [[{visit_label}]] |")
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return is_new


def _write_sources(
    visits: list[VisitRecord],
    source_pdf_path: Path,
    vault_path: Path,
    config: Config,
    manifest: Optional[ProcessingManifest] = None,
) -> None:
    """Write source files: copy PDF, save OCR text, save manifest."""
    obs = config.obsidian
    sources_dir = config.sources_dir(vault_path)

    # Copy PDF to Sources/pdfs/
    pdf_dest = sources_dir / "pdfs" / source_pdf_path.name
    if not pdf_dest.exists():
        shutil.copy2(str(source_pdf_path), str(pdf_dest))

    # Save OCR text per page
    pdf_stem = source_pdf_path.stem
    ocr_dir = sources_dir / "ocr" / sanitize_filename(pdf_stem)
    ocr_dir.mkdir(parents=True, exist_ok=True)

    for visit in visits:
        for page_idx, text in visit.raw_text_by_page.items():
            page_file = ocr_dir / f"page_{page_idx + 1:03d}.txt"
            page_file.write_text(text, encoding="utf-8")

    # Save manifest
    if manifest:
        manifest_file = sources_dir / "manifests" / f"{sanitize_filename(pdf_stem)}.json"
        manifest_file.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )


def _group_visits_by_patient(visits: list[VisitRecord]) -> dict[str, list[VisitRecord]]:
    """Group visits by patient name."""
    groups: dict[str, list[VisitRecord]] = {}
    for v in visits:
        if v.patient_name not in groups:
            groups[v.patient_name] = []
        groups[v.patient_name].append(v)
    return groups


def _format_page_range(pages: list[int]) -> str:
    """Format a list of 0-based page indices as a human-readable range."""
    if not pages:
        return ""
    # Convert to 1-based
    pages_1 = sorted(p + 1 for p in pages)
    if len(pages_1) == 1:
        return str(pages_1[0])
    # Check if consecutive
    if pages_1[-1] - pages_1[0] == len(pages_1) - 1:
        return f"{pages_1[0]}-{pages_1[-1]}"
    return ", ".join(str(p) for p in pages_1)


def _confidence_label(conf: float) -> str:
    """Convert confidence float to a human-readable label."""
    if conf >= 0.9:
        return "high"
    elif conf >= 0.7:
        return "medium"
    else:
        return "low"
