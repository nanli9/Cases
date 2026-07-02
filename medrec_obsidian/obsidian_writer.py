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
from .notes import render_note, write_note_preserving
from .utils import (
    formula_note_name,
    sanitize_filename,
    today_str,
    visit_note_link,
)

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
        "formula_notes_created": 0,
        "formula_notes_updated": 0,
        "doctor_notes_created": 0,
        "doctor_notes_updated": 0,
    }

    # Ensure directory structure
    _ensure_vault_dirs(vault_path, config)

    # Build a cross-link index from all visits (single source of truth for
    # bidirectional links: herb<->formula<->pattern<->disease<->symptom).
    index = _build_index(visits)

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

    # Write topic notes for keywords (bidirectional, enriched from the index)
    for kw in keywords:
        created = _write_topic_note(kw, index, vault_path, config)
        if created:
            stats["topic_notes_created"] += 1
        else:
            stats["topic_notes_updated"] += 1

    # Write one note per herbal formula
    for fkey, fdata in index["formulas"].items():
        created = _write_formula_note(fdata, vault_path, config)
        if created:
            stats["formula_notes_created"] += 1
        else:
            stats["formula_notes_updated"] += 1

    # Write one note per doctor (resolves [[doctor]] links; hub for their cases)
    for doctor_name, doctor_visits in _group_visits_by_doctor(visits).items():
        created = _write_doctor_note(doctor_name, doctor_visits, vault_path, config)
        if created:
            stats["doctor_notes_created"] += 1
        else:
            stats["doctor_notes_updated"] += 1

    # Write MOC hub notes (per-axis) for graph navigation
    _write_mocs(visits, keywords, index, vault_path, config)

    # Write a Dataview dashboard (renders when the Dataview plugin is installed)
    _write_dashboard(vault_path, config)

    # Configure the graph view color-groups (merged, never clobbers user keys)
    _merge_graph_config(vault_path, config)

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
        root / obs.doctors_folder,
        root / obs.visits_folder,
        root / obs.topics_folder / obs.diseases_subfolder,
        root / obs.topics_folder / obs.symptoms_subfolder,
        root / obs.topics_folder / obs.medications_subfolder,
        root / obs.topics_folder / obs.herbs_subfolder,
        root / obs.topics_folder / obs.lab_indicators_subfolder,
        root / obs.topics_folder / obs.tcm_patterns_subfolder,
        root / obs.formulas_folder,
        root / obs.maps_folder,
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

    frontmatter, title, body = _build_visit_note(visit, config)
    return write_note_preserving(filepath, frontmatter, title, body)


def _build_visit_note_content(visit: VisitRecord, config: Config) -> str:
    """Render a standalone visit note to markdown (no preservation merge)."""
    frontmatter, title, body = _build_visit_note(visit, config)
    return render_note(frontmatter, title, body)


def _build_visit_note(
    visit: VisitRecord, config: Config
) -> tuple[dict, str, list[str]]:
    """Build the (frontmatter, title, body_lines) for a visit note."""
    tag_prefix = config.obsidian.tag_prefix

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

    title = f"{visit.patient_name} -- {visit.visit_date.isoformat()} 就诊记录"
    lines: list[str] = []

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
                fname = formula_note_name(
                    formula.formula_id, visit.patient_name, visit.visit_date.isoformat()
                )
                lines.append(
                    f"> **方剂**: [[{fname}]] | **方号**: {formula.formula_id} | **贴数**: {formula.dose_count}"
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

    return frontmatter, title, lines


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

    # Identity
    lines.append(f"**性别**: {first.sex.value} | **门诊号**: {', '.join(reg_numbers)}")
    lines.append("")

    # 关键词汇总
    lines.append("## 关键词汇总")
    lines.append("")

    if all_western_diags or all_tcm_diags:
        lines.append("疾病：")
        for d in all_western_diags + all_tcm_diags:
            lines.append(f"- [[{d}]]")
        lines.append("")

    if all_symptoms:
        lines.append("症状：")
        for s in all_symptoms:
            lines.append(f"- [[{s}]]")
        lines.append("")

    if all_medications:
        lines.append("药物：")
        for m in all_medications:
            lines.append(f"- [[{m}]]")
        lines.append("")

    if all_herbs:
        lines.append("中药：")
        for h in all_herbs:
            lines.append(f"- [[{h}]]")
        lines.append("")

    # 就诊记录
    lines.append("## 就诊记录")
    lines.append("")
    for v in sorted(visits, key=lambda x: x.visit_date, reverse=True):
        pdf_stem = Path(v.source_pdf).stem if v.source_pdf else "unknown"
        visit_link = f"{v.patient_name}/{v.visit_date.isoformat()}__{sanitize_filename(pdf_stem)}"
        diags = ", ".join(d.name for d in v.tcm_diagnoses + v.western_diagnoses)
        lines.append(
            f"### {v.visit_date.isoformat()} — {v.hospital}"
        )
        lines.append("")
        lines.append(f"来源：[[{visit_link}]]")
        lines.append(f"页码：{_format_page_range(v.source_pages)}")
        lines.append(f"提取可信度：{_confidence_label(v.extraction_confidence)}")
        lines.append("")
        if v.chief_complaint:
            lines.append(f"#### 主诉")
            lines.append(v.chief_complaint)
            lines.append("")
        if diags:
            lines.append(f"#### 诊断")
            if v.tcm_diagnoses:
                lines.append("中医：")
                for d in v.tcm_diagnoses:
                    lines.append(f"- [[{d.name}]]")
            if v.western_diagnoses:
                lines.append("西医：")
                for d in v.western_diagnoses:
                    lines.append(f"- [[{d.name}]]")
            lines.append("")

    return write_note_preserving(filepath, frontmatter, patient_name, lines)


def _build_index(visits: list[VisitRecord]) -> dict:
    """Build a cross-link index from all visits.

    Returns a dict of sub-indexes keyed by entity name, capturing the
    理法方药 relationships (disease → pattern → principle → formula → herb)
    plus symptom associations, so topic notes can link in both directions.
    """
    formulas: dict[str, dict] = {}
    herb: dict[str, dict] = {}
    pattern: dict[str, dict] = {}
    disease: dict[str, dict] = {}
    symptom: dict[str, dict] = {}

    for v in visits:
        vlink = visit_note_link(v.patient_name, v.visit_date.isoformat(), v.source_pdf)
        tcm_names = [d.name for d in v.tcm_diagnoses]
        western_names = [d.name for d in v.western_diagnoses]
        patterns_here = [n for n in tcm_names if n.endswith("证")]
        diseases_here = [n for n in tcm_names if not n.endswith("证")] + western_names
        symptoms_here = list(v.symptoms)
        principle = v.treatment_principle or ""
        meds_here = [m.name for m in v.medications] + [
            m.name for m in v.chinese_patent_medicines
        ]

        for p in patterns_here:
            e = pattern.setdefault(
                p, {"symptoms": set(), "formulas": set(), "diseases": set(), "principles": set()}
            )
            e["symptoms"].update(symptoms_here)
            e["diseases"].update(diseases_here)
            if principle:
                e["principles"].add(principle)

        for d in diseases_here:
            e = disease.setdefault(
                d, {"patterns": set(), "symptoms": set(), "formulas": set(), "medications": set()}
            )
            e["patterns"].update(patterns_here)
            e["symptoms"].update(symptoms_here)
            e["medications"].update(meds_here)

        for s in symptoms_here:
            e = symptom.setdefault(s, {"patterns": set(), "diseases": set()})
            e["patterns"].update(patterns_here)
            e["diseases"].update(diseases_here)

        for f in v.herbal_formulas:
            fname = formula_note_name(
                f.formula_id, v.patient_name, v.visit_date.isoformat()
            )
            herb_names = [h.name for h in f.herbs]
            formulas[fname] = {
                "name": fname,
                "formula_id": f.formula_id,
                "patient": v.patient_name,
                "visit_date": v.visit_date.isoformat(),
                "visit_link": vlink,
                "dose_count": f.dose_count,
                "herbs": [(h.name, h.dosage) for h in f.herbs],
                "tcm": tcm_names,
                "western": western_names,
            }
            for p in patterns_here:
                pattern[p]["formulas"].add(fname)
            for d in diseases_here:
                disease[d]["formulas"].add(fname)
            for h in f.herbs:
                he = herb.setdefault(
                    h.name,
                    {"formulas": set(), "co_herbs": set(), "patterns": set(), "diseases": set(), "dosages": set()},
                )
                he["formulas"].add(fname)
                he["co_herbs"].update(n for n in herb_names if n != h.name)
                he["patterns"].update(patterns_here)
                he["diseases"].update(diseases_here)
                if h.dosage:
                    he["dosages"].add(h.dosage)

    return {
        "formulas": formulas,
        "herb": herb,
        "pattern": pattern,
        "disease": disease,
        "symptom": symptom,
    }


def _links(names) -> list[str]:
    """Render a collection of names as a sorted list of wikilink strings."""
    return [f"[[{n}]]" for n in sorted(names)]


def _dedupe_occurrences(kw: Keyword) -> list:
    """De-duplicate occurrences on (patient, visit_link, detail)."""
    seen: set = set()
    out = []
    for o in kw.occurrences:
        key = (o.patient, o.visit_link, o.detail)
        if key not in seen:
            seen.add(key)
            out.append(o)
    return out


def _occurrence_table(occurrences: list, detail_header: Optional[str] = None) -> list[str]:
    """Render occurrences as a markdown table with real, resolvable visit links."""
    lines: list[str] = []
    if detail_header:
        lines.append(f"| 患者 | 就诊 | {detail_header} |")
        lines.append("|------|------|------|")
        for o in occurrences:
            lines.append(
                f"| [[{o.patient}]] | [[{o.visit_link}\\|{o.visit_date}]] | {o.detail} |"
            )
    else:
        lines.append("| 患者 | 就诊 |")
        lines.append("|------|------|")
        for o in occurrences:
            lines.append(f"| [[{o.patient}]] | [[{o.visit_link}\\|{o.visit_date}]] |")
    return lines


def _write_topic_note(
    keyword: Keyword, index: dict, vault_path: Path, config: Config
) -> bool:
    """Write or update an enriched, bidirectional topic note. Returns True if new."""
    obs = config.obsidian
    root = config.vault_root(vault_path)
    tag_prefix = obs.tag_prefix

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

    filepath = topic_dir / f"{sanitize_filename(keyword.term)}.md"

    occ = _dedupe_occurrences(keyword)
    visit_count = len({o.visit_link for o in occ})

    frontmatter: dict = {
        "type": keyword.type.value,
        "name": keyword.term,
        "aliases": keyword.aliases,
    }
    body: list[str] = []

    if keyword.type == KeywordType.HERB:
        h = index["herb"].get(keyword.term, {})
        frontmatter["方剂"] = _links(h.get("formulas", set()))
        frontmatter["相关证型"] = _links(h.get("patterns", set()))
        frontmatter["剂量"] = sorted(h.get("dosages", set()))
        frontmatter["出现次数"] = visit_count
        # Reference fields left blank for the user to fill while studying.
        frontmatter["性味"] = ""
        frontmatter["归经"] = []
        frontmatter["功效分类"] = ""
        if h.get("formulas"):
            body += ["## 所属方剂", ""] + [f"- {l}" for l in _links(h["formulas"])] + [""]
        if h.get("dosages"):
            body += ["## 常用剂量", "", "、".join(sorted(h["dosages"])), ""]
        if h.get("co_herbs"):
            body += ["## 同方常用药", ""] + [f"- {l}" for l in _links(h["co_herbs"])] + [""]
        if h.get("patterns"):
            body += ["## 相关证型", ""] + [f"- {l}" for l in _links(h["patterns"])] + [""]

    elif keyword.type == KeywordType.TCM_PATTERN:
        p = index["pattern"].get(keyword.term, {})
        frontmatter["常见症状"] = _links(p.get("symptoms", set()))
        frontmatter["相关方剂"] = _links(p.get("formulas", set()))
        frontmatter["相关疾病"] = _links(p.get("diseases", set()))
        frontmatter["出现次数"] = visit_count
        frontmatter["治法"] = "；".join(sorted(p.get("principles", set())))
        if p.get("symptoms"):
            body += ["## 常见症状", ""] + [f"- {l}" for l in _links(p["symptoms"])] + [""]
        if p.get("formulas"):
            body += ["## 相关方剂", ""] + [f"- {l}" for l in _links(p["formulas"])] + [""]
        if p.get("diseases"):
            body += ["## 相关疾病", ""] + [f"- {l}" for l in _links(p["diseases"])] + [""]

    elif keyword.type == KeywordType.DISEASE:
        d = index["disease"].get(keyword.term, {})
        frontmatter["相关证型"] = _links(d.get("patterns", set()))
        frontmatter["常见症状"] = _links(d.get("symptoms", set()))
        frontmatter["相关方剂"] = _links(d.get("formulas", set()))
        frontmatter["出现次数"] = visit_count
        if d.get("patterns"):
            body += ["## 相关证型", ""] + [f"- {l}" for l in _links(d["patterns"])] + [""]
        if d.get("symptoms"):
            body += ["## 常见症状", ""] + [f"- {l}" for l in _links(d["symptoms"])] + [""]
        if d.get("formulas"):
            body += ["## 相关方剂", ""] + [f"- {l}" for l in _links(d["formulas"])] + [""]
        if d.get("medications"):
            body += ["## 相关药物", ""] + [f"- {l}" for l in _links(d["medications"])] + [""]

    elif keyword.type == KeywordType.SYMPTOM:
        s = index["symptom"].get(keyword.term, {})
        frontmatter["相关证型"] = _links(s.get("patterns", set()))
        frontmatter["相关疾病"] = _links(s.get("diseases", set()))
        frontmatter["出现次数"] = visit_count
        if s.get("patterns"):
            body += ["## 相关证型", ""] + [f"- {l}" for l in _links(s["patterns"])] + [""]
        if s.get("diseases"):
            body += ["## 相关疾病", ""] + [f"- {l}" for l in _links(s["diseases"])] + [""]
    else:
        frontmatter["出现次数"] = visit_count

    frontmatter["tags"] = [f"{tag_prefix}/{keyword.type.value}"]

    # Occurrence table (with real, resolvable visit links)
    detail_header = None
    if keyword.type == KeywordType.HERB:
        detail_header = "剂量"
    elif keyword.type == KeywordType.LAB_INDICATOR:
        detail_header = "结果"
    if occ:
        body += ["## 出现记录", ""] + _occurrence_table(occ, detail_header) + [""]

    return write_note_preserving(filepath, frontmatter, keyword.term, body)


def _write_formula_note(fdata: dict, vault_path: Path, config: Config) -> bool:
    """Write one note per herbal formula, linking herbs, patterns and patient."""
    tag_prefix = config.obsidian.tag_prefix
    formulas_dir = config.formulas_dir(vault_path)
    formulas_dir.mkdir(parents=True, exist_ok=True)

    filepath = formulas_dir / f"{sanitize_filename(fdata['name'])}.md"

    patterns = [n for n in fdata["tcm"] if n.endswith("证")]
    diseases = [n for n in fdata["tcm"] if not n.endswith("证")] + fdata["western"]

    frontmatter = {
        "type": "formula",
        "name": fdata["name"],
        "formula_id": fdata["formula_id"],
        "patient": f"[[{fdata['patient']}]]",
        "visit_date": fdata["visit_date"],
        "贴数": fdata["dose_count"],
        "中药": [f"[[{name}]]" for name, _ in fdata["herbs"]],
        "主治证型": _links(patterns),
        "主治疾病": _links(diseases),
        "tags": [f"{tag_prefix}/formula"],
    }

    title = f"方剂 {fdata['formula_id'] or fdata['name']}"
    lines: list[str] = []
    lines.append(
        f"**患者**: [[{fdata['patient']}]] | "
        f"**就诊**: [[{fdata['visit_link']}\\|{fdata['visit_date']}]] | "
        f"**贴数**: {fdata['dose_count']}"
    )
    lines.append("")
    lines.append("## 组成")
    lines.append("")
    lines.append("| 药物 | 剂量 |")
    lines.append("|------|------|")
    for name, dosage in fdata["herbs"]:
        lines.append(f"| [[{name}]] | {dosage} |")
    lines.append("")
    if patterns or diseases:
        lines.append("## 主治")
        lines.append("")
        for l in _links(patterns) + _links(diseases):
            lines.append(f"- {l}")
        lines.append("")

    return write_note_preserving(filepath, frontmatter, title, lines)


def _write_mocs(
    visits: list[VisitRecord],
    keywords: list[Keyword],
    index: dict,
    vault_path: Path,
    config: Config,
) -> None:
    """Write per-axis Map-of-Content hub notes plus a top-level index."""
    obs = config.obsidian
    root = config.vault_root(vault_path)
    tag_prefix = obs.tag_prefix
    maps_dir = config.maps_dir(vault_path)
    maps_dir.mkdir(parents=True, exist_ok=True)

    def fm(title: str) -> str:
        data = {"type": "moc", "tags": [f"{tag_prefix}/moc"], "created": today_str()}
        block = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False).strip()
        return f"---\n{block}\n---\n\n# {title}\n"

    by_type: dict[KeywordType, list[Keyword]] = {}
    for kw in keywords:
        by_type.setdefault(kw.type, []).append(kw)

    def count(kw: Keyword) -> int:
        return len({o.visit_link for o in kw.occurrences})

    # Per-axis hubs: (filename, title, keyword type)
    axes = [
        ("疾病总览", "疾病总览", KeywordType.DISEASE),
        ("证型总览", "证型总览", KeywordType.TCM_PATTERN),
        ("症状总览", "症状总览", KeywordType.SYMPTOM),
        ("中药总览", "中药总览", KeywordType.HERB),
        ("化验指标总览", "化验指标总览", KeywordType.LAB_INDICATOR),
        ("药物总览", "药物总览", KeywordType.MEDICATION),
    ]
    for filename, title, ktype in axes:
        kws = sorted(by_type.get(ktype, []), key=lambda k: (-count(k), k.term))
        lines = [fm(title), ""]
        for kw in kws:
            lines.append(f"- [[{kw.term}]] ×{count(kw)}")
        (maps_dir / f"{filename}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Formulas hub
    lines = [fm("方剂总览"), ""]
    for fname, fdata in sorted(index["formulas"].items()):
        lines.append(
            f"- [[{fname}]] — [[{fdata['patient']}]]（{fdata['visit_date']}，{fdata['dose_count']}贴）"
        )
    (maps_dir / "方剂总览.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Top-level index
    patients = _group_visits_by_patient(visits)
    lines = [fm("知识图谱总览"), ""]
    lines.append("## 导航")
    lines.append("")
    for name in ["疾病总览", "证型总览", "方剂总览", "中药总览", "症状总览", "化验指标总览", "药物总览"]:
        lines.append(f"- [[{name}]]")
    lines.append("- [[Dashboard]]")
    lines.append("")
    lines.append("## 患者")
    lines.append("")
    for name, pvs in patients.items():
        dates = ", ".join(v.visit_date.isoformat() for v in sorted(pvs, key=lambda x: x.visit_date))
        lines.append(f"- [[{name}]]（{dates}）")
    lines.append("")
    (root / "知识图谱总览.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_dashboard(vault_path: Path, config: Config) -> None:
    """Write a Dataview dashboard (renders when the Dataview plugin is enabled)."""
    tag_prefix = config.obsidian.tag_prefix
    maps_dir = config.maps_dir(vault_path)
    maps_dir.mkdir(parents=True, exist_ok=True)

    p = tag_prefix
    content = f"""---
type: dashboard
tags:
- {p}/moc
---

# Dashboard

> [!note] 需要安装并启用 **Dataview** 插件才能渲染下面的动态视图。
> 未安装时可改用 [[知识图谱总览]] 中的静态导航。

## 高频中药（按出现次数）

```dataview
TABLE 出现次数, 剂量, 相关证型
FROM #{p}/herb
SORT 出现次数 DESC
```

## 证型 → 方剂 → 症状

```dataview
TABLE 相关方剂 AS 方剂, 常见症状 AS 症状, 治法
FROM #{p}/tcm_pattern
SORT file.name ASC
```

## 方剂一览

```dataview
TABLE patient AS 患者, visit_date AS 就诊, 贴数, 主治证型
FROM #{p}/formula
SORT visit_date DESC
```

## 疾病 → 证型

```dataview
TABLE 相关证型, 常见症状, 出现次数
FROM #{p}/disease
SORT 出现次数 DESC
```
"""
    (maps_dir / "Dashboard.md").write_text(content, encoding="utf-8")


# Graph-view color groups by entity tag (rgb stored as an integer, per Obsidian).
_GRAPH_COLORS = {
    "patient": 0x4E79A7,
    "doctor": 0xBAB0AC,
    "visit": 0x9C755F,
    "disease": 0xE15759,
    "tcm_pattern": 0xB07AA1,
    "formula": 0x59A14F,
    "herb": 0x8CD17D,
    "symptom": 0xF28E2B,
    "medication": 0x76B7B2,
    "lab_indicator": 0xEDC948,
}


def _merge_graph_config(vault_path: Path, config: Config) -> None:
    """Merge entity color-groups into .obsidian/graph.json without clobbering.

    Wrapped defensively: graph config is a nicety, never fail generation over it.
    """
    tag_prefix = config.obsidian.tag_prefix
    graph_path = config.vault_root(vault_path) / ".obsidian" / "graph.json"
    try:
        data: dict = {}
        if graph_path.exists():
            data = json.loads(graph_path.read_text(encoding="utf-8"))
        groups = [
            {"query": f"tag:#{tag_prefix}/{name}", "color": {"a": 1, "rgb": rgb}}
            for name, rgb in _GRAPH_COLORS.items()
        ]
        # Preserve any user-defined groups that aren't ours.
        ours = {g["query"] for g in groups}
        existing = [
            g for g in data.get("colorGroups", []) if g.get("query") not in ours
        ]
        data["colorGroups"] = groups + existing
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        graph_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Could not update graph.json: %s", e)


def _write_sources(
    visits: list[VisitRecord],
    source_pdf_path: Path,
    vault_path: Path,
    config: Config,
    manifest: Optional[ProcessingManifest] = None,
) -> None:
    """Write source files: copy PDF to vault."""
    sources_dir = config.sources_dir(vault_path)

    # Copy PDF to Sources/pdfs/
    pdf_dest = sources_dir / "pdfs" / source_pdf_path.name
    if not pdf_dest.exists():
        shutil.copy2(str(source_pdf_path), str(pdf_dest))


def _group_visits_by_patient(visits: list[VisitRecord]) -> dict[str, list[VisitRecord]]:
    """Group visits by patient name."""
    groups: dict[str, list[VisitRecord]] = {}
    for v in visits:
        if v.patient_name not in groups:
            groups[v.patient_name] = []
        groups[v.patient_name].append(v)
    return groups


def _group_visits_by_doctor(visits: list[VisitRecord]) -> dict[str, list[VisitRecord]]:
    """Group visits by doctor name (skips visits with no doctor recorded)."""
    groups: dict[str, list[VisitRecord]] = {}
    for v in visits:
        if v.doctor:
            groups.setdefault(v.doctor, []).append(v)
    return groups


def _write_doctor_note(
    doctor_name: str,
    visits: list[VisitRecord],
    vault_path: Path,
    config: Config,
) -> bool:
    """Write a doctor hub note listing their patients and visits."""
    tag_prefix = config.obsidian.tag_prefix
    doctors_dir = config.doctors_dir(vault_path)
    doctors_dir.mkdir(parents=True, exist_ok=True)

    filepath = doctors_dir / f"{sanitize_filename(doctor_name)}.md"

    patients = sorted({v.patient_name for v in visits})
    frontmatter = {
        "type": "doctor",
        "name": doctor_name,
        "患者": [f"[[{p}]]" for p in patients],
        "接诊次数": len(visits),
        "tags": [f"{tag_prefix}/doctor"],
    }

    lines: list[str] = []
    lines.append("## 接诊记录")
    lines.append("")
    lines.append("| 患者 | 就诊 |")
    lines.append("|------|------|")
    for v in sorted(visits, key=lambda x: x.visit_date, reverse=True):
        vlink = visit_note_link(v.patient_name, v.visit_date.isoformat(), v.source_pdf)
        lines.append(f"| [[{v.patient_name}]] | [[{vlink}\\|{v.visit_date.isoformat()}]] |")
    lines.append("")

    return write_note_preserving(filepath, frontmatter, doctor_name, lines)


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
        return "高"
    elif conf >= 0.7:
        return "中"
    else:
        return "低"
