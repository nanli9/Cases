"""Deterministic keyword and entity extraction from parsed visit records.

All extraction is rule-based (regex + dictionary). No LLM calls.
"""

from __future__ import annotations

import logging
import re

from .models import (
    ChinesePatentMedicine,
    Diagnosis,
    ExamOrder,
    Herb,
    HerbalFormula,
    Keyword,
    KeywordType,
    LabResult,
    Relation,
    RelationType,
    VisitRecord,
    WesternMedication,
)

logger = logging.getLogger(__name__)

# ── Symptom dictionary (expandable) ──────────────────────────────────────

SYMPTOM_DICT: set[str] = {
    # Head/neurological
    "头晕", "头痛", "眩晕", "头胀痛", "偏头痛", "头部胀痛",
    "视物模糊", "视力下降", "耳鸣", "听力下降",
    "失眠", "入睡困难", "多梦", "眠差", "睡眠障碍",
    "手颤", "震颤", "肢体震颤", "行走不稳",
    # Cardiovascular
    "胸闷", "胸痛", "心悸", "气短", "气促",
    # Gastrointestinal
    "恶心", "呕吐", "腹胀", "腹痛", "纳差", "食欲不振",
    "口干", "口苦", "便秘", "腹泻",
    # Musculoskeletal
    "腰痛", "关节痛", "肢体疼痛", "肌肉萎缩",
    "手臂串痛", "肢体乏力", "手部疼痛",
    # General
    "乏力", "疲劳", "周身乏力", "倦怠",
    "手脚偏凉", "手足冷", "手脚冰凉",
    "盗汗", "自汗", "水肿", "脚肿",
    # Respiratory
    "咳嗽", "咳痰", "咳白痰", "气喘", "喘息",
    # Urinary
    "尿频", "尿急", "尿痛", "小便黄",
    # TCM-specific symptoms
    "面色苍白", "面色红", "唇色红",
    "舌质淡", "舌淡", "舌紫黑", "舌嫩红", "舌胖",
    "苔白腻", "苔薄黄", "苔黄腻", "苔水滑",
    "眼前发黑", "闷痛",
    "情绪急躁", "烦躁", "焦虑",
    "四肢量改善",
}

# ── Imaging examination keywords ──────────────────────────────────────

IMAGING_KEYWORDS: set[str] = {
    "MRI", "MRA", "DWI", "SWI", "CT", "X线", "B超", "超声",
    "磁共振", "头部磁共振", "头MRA", "脑MRI",
    "心电图", "脑电图", "肌电图",
}


def extract_all(visit: VisitRecord) -> VisitRecord:
    """Run all extractors on a VisitRecord, populating structured fields.

    This modifies the visit in-place and returns it.
    """
    # 1. Extract diagnoses from the diagnosis section
    _extract_diagnoses(visit)

    # 2. Extract treatment plan components
    _extract_treatment_plan(visit)

    # 3. Extract lab results from follow-ups and present illness
    _extract_lab_results(visit)

    # 4. Extract symptoms from chief complaint and present illness
    _extract_symptoms(visit)

    # 5. Populate diseases list from diagnoses
    _populate_diseases(visit)

    # 6. Populate herbs list from herbal formulas
    _populate_herbs_list(visit)

    # 7. Extract imaging references
    _extract_imaging(visit)

    return visit


def extract_keywords(visits: list[VisitRecord]) -> list[Keyword]:
    """Extract all unique keywords across visits."""
    keywords_map: dict[str, Keyword] = {}

    for visit in visits:
        visit_label = f"{visit.patient_name}_{visit.visit_date.isoformat()}"

        # Diseases from diagnoses
        for diag in visit.tcm_diagnoses + visit.western_diagnoses:
            _add_keyword(
                keywords_map,
                diag.name,
                KeywordType.DISEASE
                if not _is_tcm_pattern(diag.name)
                else KeywordType.TCM_PATTERN,
                visit.patient_name,
                visit_label,
                visit.source_pages,
            )

        # Symptoms
        for symptom in visit.symptoms:
            _add_keyword(
                keywords_map,
                symptom,
                KeywordType.SYMPTOM,
                visit.patient_name,
                visit_label,
                visit.source_pages,
            )

        # Herbs
        for formula in visit.herbal_formulas:
            for herb in formula.herbs:
                _add_keyword(
                    keywords_map,
                    herb.name,
                    KeywordType.HERB,
                    visit.patient_name,
                    visit_label,
                    visit.source_pages,
                )

        # Medications
        for med in visit.medications:
            _add_keyword(
                keywords_map,
                med.name,
                KeywordType.MEDICATION,
                visit.patient_name,
                visit_label,
                visit.source_pages,
            )
        for med in visit.chinese_patent_medicines:
            _add_keyword(
                keywords_map,
                med.name,
                KeywordType.MEDICATION,
                visit.patient_name,
                visit_label,
                visit.source_pages,
            )

        # Lab indicators
        for lab in visit.labs:
            term = lab.chinese_name
            if lab.abbreviation:
                term = f"{lab.chinese_name}({lab.abbreviation})"
            _add_keyword(
                keywords_map,
                term,
                KeywordType.LAB_INDICATOR,
                visit.patient_name,
                visit_label,
                visit.source_pages,
            )

    return list(keywords_map.values())


def extract_relations(visits: list[VisitRecord]) -> list[Relation]:
    """Extract relations between entities across all visits."""
    relations: list[Relation] = []

    # Collect per-visit disease-symptom pairs
    disease_symptom_map: dict[str, set[str]] = {}

    for visit in visits:
        all_diags = [d.name for d in visit.tcm_diagnoses + visit.western_diagnoses]
        visit_label = f"{visit.patient_name}_{visit.visit_date.isoformat()}"

        # disease_has_symptom
        for diag_name in all_diags:
            if diag_name not in disease_symptom_map:
                disease_symptom_map[diag_name] = set()
            for symptom in visit.symptoms:
                disease_symptom_map[diag_name].add(symptom)
                relations.append(
                    Relation(
                        source_term=diag_name,
                        target_term=symptom,
                        relation_type=RelationType.DISEASE_HAS_SYMPTOM,
                        evidence=[f"Visit: {visit_label}"],
                        source_pages=visit.source_pages,
                    )
                )

        # disease_treated_by_medication
        all_meds = [m.name for m in visit.medications + visit.chinese_patent_medicines]
        all_herb_names = []
        for formula in visit.herbal_formulas:
            all_herb_names.extend(h.name for h in formula.herbs)

        for diag_name in all_diags:
            for med_name in all_meds:
                relations.append(
                    Relation(
                        source_term=diag_name,
                        target_term=med_name,
                        relation_type=RelationType.DISEASE_TREATED_BY_MEDICATION,
                        evidence=[f"Visit: {visit_label}"],
                        source_pages=visit.source_pages,
                    )
                )

        # patient_has_disease
        for diag_name in all_diags:
            relations.append(
                Relation(
                    source_term=visit.patient_name,
                    target_term=diag_name,
                    relation_type=RelationType.PATIENT_HAS_DISEASE,
                    evidence=[f"Visit: {visit_label}"],
                    source_pages=visit.source_pages,
                )
            )

    # diseases_share_symptom: find diseases that share symptoms across patients
    disease_names = list(disease_symptom_map.keys())
    for i in range(len(disease_names)):
        for j in range(i + 1, len(disease_names)):
            d1, d2 = disease_names[i], disease_names[j]
            shared = disease_symptom_map[d1] & disease_symptom_map[d2]
            if shared:
                relations.append(
                    Relation(
                        source_term=d1,
                        target_term=d2,
                        relation_type=RelationType.DISEASES_SHARE_SYMPTOM,
                        evidence=[f"Shared symptoms: {', '.join(shared)}"],
                    )
                )

    # Deduplicate relations
    return _deduplicate_relations(relations)


# ── Internal extraction functions ────────────────────────────────────────


def _extract_diagnoses(visit: VisitRecord) -> None:
    """Extract TCM and Western diagnoses from raw text sections."""
    # The diagnosis section should have been parsed by the parser.
    # We need to find it in the concatenated raw text.
    full_text = "\n".join(visit.raw_text_by_page.values())

    # Find the diagnosis block
    diag_match = re.search(r"初步诊断[：:]\s*(?:中医诊断[：:])?", full_text)
    if not diag_match:
        return

    diag_text = full_text[diag_match.end():]

    # Truncate at next major section (处置, 注意事项)
    for end_pattern in [r"处\s*置[：:]", r"注意事项[：:]"]:
        end_m = re.search(end_pattern, diag_text)
        if end_m:
            diag_text = diag_text[:end_m.start()]
            break

    # Split into TCM and Western
    western_split = re.search(r"西医诊断[：:]", diag_text)
    if western_split:
        tcm_text = diag_text[:western_split.start()]
        western_text = diag_text[western_split.end():]
    else:
        tcm_text = diag_text
        western_text = ""

    visit.tcm_diagnoses = _parse_numbered_diagnoses(tcm_text)
    visit.western_diagnoses = _parse_numbered_diagnoses(western_text)


def _parse_numbered_diagnoses(text: str) -> list[Diagnosis]:
    """Parse numbered diagnosis items from text.

    Handles formats:
      1.眩晕   2.气血亏虚证
      1.单纯手震颤|特发性震颤
      1.偏头痛不伴有先兆[普通偏头痛]
      1.高血压1级|极高危组
    """
    diagnoses: list[Diagnosis] = []
    if not text.strip():
        return diagnoses

    # Find all numbered items: digit followed by . or 、
    # Use a pattern that captures the number and the following text until the
    # next numbered item or end of string
    items = re.findall(
        r"(\d+)\s*[.、．]\s*((?:(?!\d+\s*[.、．]).)+)",
        text,
        re.DOTALL,
    )

    for idx_str, raw_name in items:
        raw_name = raw_name.strip()
        # Clean up: remove trailing whitespace, newlines
        raw_name = re.sub(r"\s+", "", raw_name)

        if not raw_name:
            continue

        # Parse qualifier: check for | or []
        name, qualifier = _parse_diagnosis_qualifier(raw_name)

        diagnoses.append(
            Diagnosis(
                index=int(idx_str),
                name=name,
                qualifier=qualifier,
            )
        )

    return diagnoses


def _parse_diagnosis_qualifier(raw: str) -> tuple[str, str | None]:
    """Split a diagnosis name from its qualifier.

    Handles:
      "单纯手震颤|特发性震颤" -> ("单纯手震颤", "特发性震颤")
      "偏头痛不伴有先兆[普通偏头痛]" -> ("偏头痛不伴有先兆", "普通偏头痛")
      "高血压1级|极高危组" -> ("高血压1级", "极高危组")
      "脑梗死|恢复期" -> ("脑梗死", "恢复期")
      "尿潴留|留置导尿管" -> ("尿潴留", "留置导尿管")
    """
    # Check for [] bracket qualifier
    m = re.match(r"(.+?)[\[【](.+?)[\]】]", raw)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # Check for | pipe qualifier
    if "|" in raw or "｜" in raw:
        parts = re.split(r"[|｜]", raw, maxsplit=1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()

    return raw, None


def _extract_treatment_plan(visit: VisitRecord) -> None:
    """Extract exam orders, medications, patent medicines, and herbal formulas."""
    full_text = "\n".join(visit.raw_text_by_page.values())

    # Find treatment plan section
    treat_match = re.search(r"处\s*置[：:]", full_text)
    if not treat_match:
        return

    treat_text = full_text[treat_match.end():]

    # Truncate at 注意事项
    notes_match = re.search(r"注意事项[：:]", treat_text)
    if notes_match:
        treat_text = treat_text[:notes_match.start()]

    # Extract exam orders (检查 section)
    visit.exam_orders = _extract_exam_orders(treat_text)

    # Extract western medications
    visit.medications = _extract_western_meds(treat_text)

    # Extract Chinese patent medicines
    visit.chinese_patent_medicines = _extract_patent_meds(treat_text)

    # Extract herbal formulas
    visit.herbal_formulas = _extract_herbal_formulas(treat_text)


def _extract_exam_orders(text: str) -> list[ExamOrder]:
    """Extract examination/test orders from treatment text."""
    orders: list[ExamOrder] = []

    # Find the exam section -- starts with 检查: or numbered items before any prescription
    exam_block = text
    # Try to truncate at first prescription marker
    for marker in ["西药处方", "中成药处方", "草药方"]:
        idx = exam_block.find(marker)
        if idx >= 0:
            exam_block = exam_block[:idx]
            break

    # Parse numbered exam items: "1.生化（22）    360"
    items = re.findall(
        r"(\d+)\s*[.、]\s*([\u4e00-\u9fff\w（）\(\)+\-\s]+?)\s+(\d+(?:\.\d+)?)",
        exam_block,
    )
    for _, name, cost in items:
        name = name.strip()
        if name and any(c >= "\u4e00" for c in name):
            orders.append(
                ExamOrder(name=name, cost=float(cost))
            )

    return orders


def _extract_western_meds(text: str) -> list[WesternMedication]:
    """Extract western medication prescriptions."""
    meds: list[WesternMedication] = []

    # Find 西药处方 block
    m = re.search(r"西药处方", text)
    if not m:
        return meds

    med_block = text[m.end():]
    # Truncate at next section
    for marker in ["中成药处方", "草药方", "注意事项"]:
        idx = med_block.find(marker)
        if idx >= 0:
            med_block = med_block[:idx]
            break

    # Parse medication lines
    # Pattern: drug_name(spec) quantity frequency dose route
    lines = med_block.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try to match the standard prescription format
        med = _parse_medication_line(line)
        if med:
            meds.append(WesternMedication(**med))

    return meds


def _parse_medication_line(line: str) -> dict | None:
    """Parse a single medication prescription line."""
    # Pattern: {name}({spec}) {qty}盒/{unit} {freq} {dose} {route}
    m = re.match(
        r"([\u4e00-\u9fff\w]+(?:片|胶囊|丸|颗粒|口服液|注射液|散|膏|栓|滴丸|溶片|冲剂)?)"
        r"\s*[（\(](.+?)[）\)]"
        r"\s+([\d.]+\S*)"
        r"\s+([\S]+(?:\s*[\(（][\d\-]+[\)）])?)"
        r"\s+([\d.]+\s*[\(（]\S+?[\)）])"
        r"\s*(口服|外用|注射|静脉|皮下|肌注|含服)?",
        line,
    )
    if m:
        return {
            "name": m.group(1).strip(),
            "specification": m.group(2).strip(),
            "quantity": m.group(3).strip(),
            "frequency": m.group(4).strip(),
            "single_dose": m.group(5).strip(),
            "route": m.group(6).strip() if m.group(6) else "口服",
        }

    # Simpler fallback pattern
    m2 = re.match(
        r"([\u4e00-\u9fff\w]+(?:片|胶囊|丸|颗粒|口服液|注射液|散|膏|溶片))"
        r"\s*[（\(](.+?)[）\)]\s+(.+)",
        line,
    )
    if m2:
        rest = m2.group(3).strip()
        return {
            "name": m2.group(1).strip(),
            "specification": m2.group(2).strip(),
            "quantity": "",
            "frequency": "",
            "single_dose": "",
            "route": "口服" if "口服" in rest else "",
        }

    return None


def _extract_patent_meds(text: str) -> list[ChinesePatentMedicine]:
    """Extract Chinese patent medicine prescriptions."""
    meds: list[ChinesePatentMedicine] = []

    # Find 中成药处方 block
    m = re.search(r"中成药处方", text)
    if not m:
        return meds

    med_block = text[m.end():]
    # Truncate at next section
    for marker in ["草药方", "注意事项"]:
        idx = med_block.find(marker)
        if idx >= 0:
            med_block = med_block[:idx]
            break

    lines = med_block.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parsed = _parse_medication_line(line)
        if parsed:
            meds.append(ChinesePatentMedicine(**parsed))

    return meds


def _extract_herbal_formulas(text: str) -> list[HerbalFormula]:
    """Extract herbal formula prescriptions.

    Format:
      草药方 43622340 贴数：7
      姜半夏12.00g    桂枝12.00g    茯苓30.00g    麸炒白术15.00g
      ...
    """
    formulas: list[HerbalFormula] = []

    # Find all formula blocks
    formula_starts = list(re.finditer(
        r"草药方\s+(\d+)\s+贴数[：:]\s*(\d+)",
        text,
    ))

    if not formula_starts:
        return formulas

    for i, m in enumerate(formula_starts):
        formula_id = m.group(1)
        dose_count = int(m.group(2))

        # Get the text block for this formula
        start = m.end()
        if i + 1 < len(formula_starts):
            end = formula_starts[i + 1].start()
        else:
            # End at next section marker or end of text
            end = len(text)
            for marker in ["中成药处方", "西药处方", "注意事项"]:
                idx = text.find(marker, start)
                if idx >= 0 and idx < end:
                    end = idx

        herb_block = text[start:end]
        herbs = _parse_herbs(herb_block)

        formulas.append(
            HerbalFormula(
                formula_id=formula_id,
                dose_count=dose_count,
                herbs=herbs,
            )
        )

    return formulas


def _parse_herbs(text: str) -> list[Herb]:
    """Parse individual herb entries from a formula text block.

    Handles:
      姜半夏12.00g    桂枝12.00g
      蜈蚣2.00条
      全蝎5.00g
    """
    herbs: list[Herb] = []

    # Match: Chinese characters followed by number and unit
    herb_pattern = re.compile(
        r"([\u4e00-\u9fff\u3400-\u4dbf]{1,8})"  # herb name (1-8 CJK chars)
        r"(\d+(?:\.\d+)?)"                        # dosage value
        r"\s*"
        r"(g|条|克|枚|对|ml|片)",                   # unit
    )

    for m in herb_pattern.finditer(text):
        name = m.group(1).strip()
        value = float(m.group(2))
        unit = m.group(3)

        # Skip if name looks like a section label or number
        if len(name) < 1 or name in ("贴数", "方号"):
            continue

        herbs.append(
            Herb(
                name=name,
                dosage=f"{m.group(2)}{unit}",
                dosage_value=value,
                dosage_unit=unit,
            )
        )

    return herbs


def _extract_lab_results(visit: VisitRecord) -> None:
    """Extract lab results from follow-up entries and present illness text."""
    all_labs: list[LabResult] = []

    # Check follow-up entries
    for follow_up in visit.follow_ups:
        labs = _parse_lab_text(follow_up.text)
        follow_up.lab_results = labs
        all_labs.extend(labs)

    # Also check the main present illness text
    if visit.present_illness:
        all_labs.extend(_parse_lab_text(visit.present_illness))

    visit.labs = all_labs


def _parse_lab_text(text: str) -> list[LabResult]:
    """Parse lab results from free text.

    Pattern A (structured):
      ★白细胞计数(WBC)13.05 *10^9/L ↑
      *总胆红素(TBIL)32.55 μmol/L ↑
    Pattern B (semi-structured):
      糖化血红蛋白7.3
      白细胞3+μmol/1
      t-PAIC:11.11
      LDL-C: 2.04
    """
    results: list[LabResult] = []

    # Pattern A: starred lab results with abbreviation in parentheses
    pattern_a = re.compile(
        r"([★\*☆]?)\s*"
        r"([\u4e00-\u9fff\w][\u4e00-\u9fff\w\-]*)"
        r"\s*[（\(]"
        r"([\w][\w\-]*)"
        r"[）\)]"
        r"\s*([\d.]+)"
        r"\s*"
        r"([^\s↑↓;；,，\d]*?)"
        r"\s*([↑↓])?"
    )

    for m in pattern_a.finditer(text):
        starred = bool(m.group(1).strip())
        results.append(
            LabResult(
                chinese_name=m.group(2).strip(),
                abbreviation=m.group(3).strip(),
                value=m.group(4).strip(),
                unit=m.group(5).strip(),
                direction=m.group(6) if m.group(6) else None,
                is_starred=starred,
            )
        )

    # Pattern B: abbreviation:value format (e.g., "LDL-C: 2.04", "t-PAIC:11.11")
    pattern_b = re.compile(
        r"([A-Za-z][\w\-/]*)[：:]\s*([\d.]+)"
    )

    # Avoid duplicating results already matched by pattern A
    matched_positions = {m.start() for m in pattern_a.finditer(text)}

    for m in pattern_b.finditer(text):
        if m.start() not in matched_positions:
            abbr = m.group(1).strip()
            results.append(
                LabResult(
                    abbreviation=abbr,
                    value=m.group(2).strip(),
                )
            )

    return results


def _extract_symptoms(visit: VisitRecord) -> None:
    """Extract symptoms from chief complaint and present illness using dictionary."""
    search_text = (visit.chief_complaint or "") + " " + (visit.present_illness or "")
    # Also include follow-up text
    for fu in visit.follow_ups:
        search_text += " " + (fu.text or "")

    found: list[str] = []
    for symptom in SYMPTOM_DICT:
        if symptom in search_text:
            found.append(symptom)

    # Sort for deterministic output
    visit.symptoms = sorted(set(found))


def _populate_diseases(visit: VisitRecord) -> None:
    """Populate the diseases list from all diagnoses."""
    diseases: list[str] = []
    for diag in visit.tcm_diagnoses + visit.western_diagnoses:
        diseases.append(diag.name)
    visit.diseases = diseases


def _populate_herbs_list(visit: VisitRecord) -> None:
    """Populate the herbs list from all herbal formulas."""
    herbs: list[str] = []
    for formula in visit.herbal_formulas:
        for herb in formula.herbs:
            if herb.name not in herbs:
                herbs.append(herb.name)
    visit.herbs = herbs


def _extract_imaging(visit: VisitRecord) -> None:
    """Extract imaging/exam references from text."""
    search_text = (visit.present_illness or "")
    for fu in visit.follow_ups:
        search_text += " " + (fu.text or "")
    search_text += " " + (visit.auxiliary_exam or "")

    found: list[str] = []
    for keyword in IMAGING_KEYWORDS:
        if keyword in search_text:
            found.append(keyword)

    visit.imaging = sorted(set(found))


def _is_tcm_pattern(name: str) -> bool:
    """Check if a diagnosis name is a TCM pattern (证) vs disease (病)."""
    tcm_pattern_markers = ["证", "虚", "实", "热", "寒", "瘀", "痰", "湿"]
    # If it ends with 证 or contains common pattern markers in final position
    if name.endswith("证"):
        return True
    if name.endswith("类病"):
        return False
    return False


def _add_keyword(
    keywords_map: dict[str, Keyword],
    term: str,
    ktype: KeywordType,
    patient: str,
    visit_label: str,
    pages: list[int],
) -> None:
    """Add or update a keyword in the map."""
    if not term:
        return
    if term not in keywords_map:
        keywords_map[term] = Keyword(
            term=term,
            type=ktype,
            source_pages=pages,
        )
    kw = keywords_map[term]
    if patient not in kw.linked_patients:
        kw.linked_patients.append(patient)
    if visit_label not in kw.linked_visits:
        kw.linked_visits.append(visit_label)


def _deduplicate_relations(relations: list[Relation]) -> list[Relation]:
    """Remove duplicate relations, merging evidence."""
    seen: dict[tuple[str, str, str], Relation] = {}
    for r in relations:
        key = (r.source_term, r.target_term, r.relation_type.value)
        if key in seen:
            # Merge evidence
            for e in r.evidence:
                if e not in seen[key].evidence:
                    seen[key].evidence.append(e)
        else:
            seen[key] = r
    return list(seen.values())
