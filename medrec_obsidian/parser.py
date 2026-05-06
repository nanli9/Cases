"""Page grouping, deduplication, and section splitting.

This module takes a list of PageText objects (one per PDF page) and:
1. Groups consecutive pages into patient-visit records.
2. Deduplicates pages with identical content.
3. Splits the concatenated text into structured sections.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .config import Config
from .models import PageText, VisitRecord, FollowUpEntry, Sex
from .utils import compute_content_hash, parse_chinese_date

logger = logging.getLogger(__name__)

# Section label patterns in the order they appear in the document.
# Each tuple: (regex_pattern, section_key)
# Patterns are designed to be robust against OCR noise:
# - Allow optional * # + prefix (OCR may garble *)
# - Allow flexible spacing between characters
# - Allow both ： and : as separators
# - Use minimal anchoring characters that OCR is likely to preserve
SECTION_PATTERNS: list[tuple[str, str]] = [
    (r"[*#\+]?\s*主\s*诉\s*[：:]", "chief_complaint"),
    (r"[*#\+]?\s*现\s*病\s*史\s*[：:]", "present_illness"),
    (r"[*#\+]?\s*(?:现.*)?病.*史\s*[：:]", "present_illness"),
    (r"[*#\+]?\s*既\s*往\s*史\s*[：:]", "past_history"),
    (r"[*#\+]?\s*过\s*敏\s*史\s*[：:]", "allergy_history"),
    (r"[*#\+]?\s*个\s*人\s*史\s*[：:]", "personal_history"),
    (r"[*#\+]?\s*家\s*族\s*史\s*[：:]", "family_history"),
    (r"生命体征\s*[：:]", "vital_signs"),
    (r"体格检查\s*[：:]", "physical_exam"),
    (r"中医四诊\s*[：:]", "tcm_four_exams"),
    (r"辨证依据\s*[：:]", "pattern_basis"),
    (r"辩证依据\s*[：:]", "pattern_basis"),  # common OCR variant
    (r"治则治法\s*[：:]", "treatment_principle"),
    (r"辅助检查\s*[：:]", "auxiliary_exam"),
    (r"初步诊断[：:]", "diagnosis"),
    (r"处\s*置[：:]", "treatment_plan"),
    (r"注意事项[：:]", "notes"),
]

# Sub-patterns within 既往史
PAST_HISTORY_PATTERNS: list[tuple[str, str]] = [
    (r"慢性病史[：:]", "chronic"),
    (r"传染病史[：:]", "infectious"),
    (r"手术[、/]外伤史[：:]", "surgical"),
]

# Date pattern for follow-up entries in 现病史
FOLLOWUP_DATE_RE = re.compile(
    r"(\d{4}[-年]\d{1,2}[-月]\d{1,2}[日]?)\s*(?:复诊|复查)[：:]?"
)

# Pattern for detecting BP
BP_RE = re.compile(r"BP[：:]\s*([\d.]+[/／][\d.]+)\s*mmHg", re.IGNORECASE)


def group_pages(pages: list[PageText], config: Config) -> list[list[PageText]]:
    """Group consecutive pages into patient-visit records.

    Pages are grouped by (patient_name, registration_number, visit_date).
    Within each group, duplicates are removed by content hash.

    Returns a list of page groups, each representing one visit.
    """
    if not pages:
        return []

    groups: list[list[PageText]] = []
    current_group: list[PageText] = []

    for page in pages:
        key = _page_group_key(page)

        if current_group:
            prev_key = _page_group_key(current_group[-1])
            if key != prev_key:
                groups.append(current_group)
                current_group = []

        current_group.append(page)

    if current_group:
        groups.append(current_group)

    # Deduplication pass
    total_dupes = 0
    if config.dedup.content_hash_dedup:
        for group in groups:
            original_count = len(group)
            _deduplicate_group(group)
            dupes = original_count - len(group)
            if dupes > 0:
                total_dupes += dupes
                patient = group[0].header.patient_name if group else "unknown"
                logger.warning(
                    "%s: %d duplicate page(s) removed", patient, dupes
                )

    if total_dupes > 0:
        logger.info("Total duplicate pages removed: %d", total_dupes)

    return groups


def _page_group_key(page: PageText) -> tuple[str, str, str]:
    """Create a grouping key for a page.

    Uses (registration_number, visit_date) as primary key when reg number exists,
    since OCR may garble patient names differently across pages of the same patient.
    Falls back to patient_name when reg number is missing.
    """
    reg = page.header.registration_number
    name = page.header.patient_name
    date_str = page.header.visit_date.isoformat()

    if reg:
        # Primary grouping by reg number + date (OCR-robust)
        return (reg, reg, date_str)
    else:
        # Fallback to name + date
        return (name, "", date_str)


def _deduplicate_group(group: list[PageText]) -> None:
    """Remove duplicate pages from a group in-place based on content hash."""
    seen_hashes: set[str] = set()
    to_keep: list[PageText] = []

    for page in group:
        h = compute_content_hash(page.body_text)
        if h not in seen_hashes:
            seen_hashes.add(h)
            to_keep.append(page)

    group.clear()
    group.extend(to_keep)


def _best_header(page_group: list[PageText]) -> "PageHeader":
    """Pick the best header from a page group.

    OCR may produce different name quality across pages.
    Choose the header with the most complete data (longest clean name,
    non-zero age, valid sex).
    """
    from .models import Sex

    best = page_group[0].header
    best_score = 0

    for p in page_group:
        h = p.header
        score = 0
        # Prefer longer CJK-only names (2-3 chars)
        name_cjk = re.sub(r"[^\u4e00-\u9fff]", "", h.patient_name)
        if 2 <= len(name_cjk) <= 4:
            score += len(name_cjk) * 10
        # Prefer non-zero age
        if h.age > 0:
            score += 5
        # Prefer known sex
        if h.sex != Sex.UNKNOWN:
            score += 5
        # Prefer non-empty department
        if h.department:
            score += 3
        # Prefer non-empty registration number
        if h.registration_number:
            score += 3

        if score > best_score:
            best_score = score
            best = h

    # Clean the name: keep only CJK characters
    clean_name = re.sub(r"[^\u4e00-\u9fff]", "", best.patient_name)
    if 2 <= len(clean_name) <= 4:
        best = best.model_copy(update={"patient_name": clean_name})

    return best


def parse_visit(
    page_group: list[PageText], source_pdf: str, hospital: str = ""
) -> VisitRecord:
    """Parse a group of pages into a VisitRecord.

    Steps:
    1. Concatenate body text from all pages.
    2. Split into sections using section label patterns.
    3. Sub-parse specific sections (past_history, diagnosis, treatment).
    4. Populate a VisitRecord with raw text and metadata.
    """
    if not page_group:
        raise ValueError("Empty page group")

    header = _best_header(page_group)

    # Build raw text by page mapping
    raw_text_by_page: dict[int, str] = {}
    for p in page_group:
        raw_text_by_page[p.pdf_page_index] = p.body_text

    # Concatenate body text with page break markers
    full_text = "\n".join(p.body_text for p in page_group)

    # Split into sections
    sections = split_sections(full_text)

    # Sub-parse past history
    chronic, infectious, surgical = _parse_past_history(
        sections.get("past_history", "")
    )

    # Sub-parse present illness for follow-ups
    present_illness_raw = sections.get("present_illness", "")
    initial_text, follow_ups = _parse_follow_ups(present_illness_raw)

    # Parse vital signs
    bp = _parse_bp(sections.get("vital_signs", ""))

    # Parse TCM four exams
    tongue, pulse = _parse_tcm_four_exams(sections.get("tcm_four_exams", ""))

    # Compute confidence
    min_confidence = min(p.confidence for p in page_group)

    # Detect warnings
    warnings: list[str] = []
    uncertain_fields: list[str] = []

    # Check for template placeholders
    for section_name, section_text in sections.items():
        if _has_template_placeholder(section_text):
            warnings.append(f"TEMPLATE_PLACEHOLDER in {section_name}")
            uncertain_fields.append(section_name)

    # Check for empty mandatory sections
    for mandatory in ["chief_complaint", "present_illness"]:
        if not sections.get(mandatory, "").strip():
            warnings.append(f"EMPTY_SECTION: {mandatory}")

    # Detect hospital from page text if not provided
    if not hospital:
        for p in page_group:
            # Look for hospital name in the first few lines
            for line in p.body_text.split("\n")[:5]:
                if "医院" in line:
                    hospital = line.strip()
                    break
            # Also check the raw full page text since body might miss header
            break
        if not hospital:
            hospital = "北京中医药大学东方医院"  # fallback from header

    return VisitRecord(
        patient_name=header.patient_name,
        sex=header.sex,
        age=header.age,
        visit_date=header.visit_date,
        hospital=hospital,
        department=header.department,
        registration_number=header.registration_number,
        fee_category=header.fee_category,
        document_id=header.document_id,
        doctor=header.doctor_name,
        chief_complaint=sections.get("chief_complaint", ""),
        present_illness=initial_text,
        follow_ups=follow_ups,
        chronic_history=chronic,
        infectious_history=infectious,
        surgical_history=surgical,
        allergy_history=sections.get("allergy_history"),
        personal_history=sections.get("personal_history"),
        family_history=sections.get("family_history"),
        vital_signs_bp=bp,
        physical_exam=sections.get("physical_exam"),
        tcm_tongue=tongue,
        tcm_pulse=pulse,
        pattern_basis=sections.get("pattern_basis"),
        treatment_principle=sections.get("treatment_principle"),
        auxiliary_exam=sections.get("auxiliary_exam"),
        notes=sections.get("notes"),
        raw_text_by_page=raw_text_by_page,
        source_pdf=source_pdf,
        source_pages=[p.pdf_page_index for p in page_group],
        extraction_confidence=min_confidence,
        uncertain_fields=uncertain_fields,
        warnings=warnings,
    )


def split_sections(text: str) -> dict[str, str]:
    """Split text into named sections using section label patterns.

    Returns a dict mapping section names to their content text.
    """
    matches: list[tuple[int, int, str]] = []

    for pattern, name in SECTION_PATTERNS:
        for m in re.finditer(pattern, text):
            matches.append((m.start(), m.end(), name))

    if not matches:
        return {"raw": text}

    # Sort by position in text
    matches.sort(key=lambda x: x[0])

    sections: dict[str, str] = {}
    for i, (start, end, name) in enumerate(matches):
        content_start = end
        content_end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()
        # If same section appears multiple times (multi-page), concatenate
        if name in sections:
            sections[name] += "\n" + content
        else:
            sections[name] = content

    return sections


def _parse_past_history(
    text: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse 既往史 into chronic, infectious, and surgical sub-sections."""
    if not text.strip():
        return None, None, None

    chronic = None
    infectious = None
    surgical = None

    # Try to find sub-labels
    parts: list[tuple[int, int, str]] = []
    for pattern, name in PAST_HISTORY_PATTERNS:
        m = re.search(pattern, text)
        if m:
            parts.append((m.start(), m.end(), name))

    if not parts:
        # No sub-labels found, treat entire text as chronic history
        cleaned = _clean_history_field(text)
        return cleaned, None, None

    parts.sort(key=lambda x: x[0])

    for i, (start, end, name) in enumerate(parts):
        content_end = parts[i + 1][0] if i + 1 < len(parts) else len(text)
        content = text[end:content_end].strip()
        content = _clean_history_field(content)

        if name == "chronic":
            chronic = content
        elif name == "infectious":
            infectious = content
        elif name == "surgical":
            surgical = content

    return chronic, infectious, surgical


def _clean_history_field(text: str) -> Optional[str]:
    """Clean a history field value, handling 无/有 patterns."""
    text = text.strip()
    if not text:
        return None

    # Remove the "无/有" prefix pattern
    text = re.sub(r"^无/有\s*", "", text).strip()

    # If just "无" or "否认", return as-is (it's meaningful)
    return text if text else None


def _parse_follow_ups(text: str) -> tuple[str, list[FollowUpEntry]]:
    """Parse 现病史 into initial visit text and dated follow-up entries.

    Returns (initial_text, list_of_follow_ups).
    """
    if not text.strip():
        return "", []

    # Find all follow-up date markers
    matches = list(FOLLOWUP_DATE_RE.finditer(text))

    if not matches:
        return text.strip(), []

    # Initial text is everything before the first follow-up
    initial_text = text[: matches[0].start()].strip()

    follow_ups: list[FollowUpEntry] = []
    for i, m in enumerate(matches):
        date_str = m.group(1)
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()

        follow_ups.append(
            FollowUpEntry(
                date_str=date_str,
                follow_date=parse_chinese_date(date_str),
                text=content,
            )
        )

    return initial_text, follow_ups


def _parse_bp(text: str) -> Optional[str]:
    """Extract blood pressure from vital signs text."""
    if not text:
        return None
    m = BP_RE.search(text)
    if m:
        return m.group(1)
    # Check for template placeholder
    if "{收缩压}" in text or "{舒张压}" in text:
        return None
    # Try simpler pattern
    m2 = re.search(r"(\d{2,3}[/／]\d{2,3})\s*(?:mmHg)?", text)
    if m2:
        return m2.group(1)
    return None


def _parse_tcm_four_exams(text: str) -> tuple[Optional[str], Optional[str]]:
    """Parse 中医四诊 into tongue (舌象) and pulse (脉象)."""
    if not text:
        return None, None

    tongue = None
    pulse = None

    m_tongue = re.search(r"舌象[：:]\s*(.*?)(?=脉象|$)", text, re.DOTALL)
    if m_tongue:
        t = m_tongue.group(1).strip()
        if t and t not in ("", "无"):
            tongue = t

    m_pulse = re.search(r"脉象[：:]\s*(.*?)$", text, re.DOTALL)
    if m_pulse:
        p = m_pulse.group(1).strip()
        if p and p not in ("", "无"):
            pulse = p

    return tongue, pulse


def _has_template_placeholder(text: str) -> bool:
    """Check if text contains unfilled template placeholders."""
    placeholders = [
        "{收缩压}",
        "{舒张压}",
        "____",
        "（单击鼠标右键选择",
    ]
    return any(p in text for p in placeholders)
