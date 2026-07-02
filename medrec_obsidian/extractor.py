"""Keyword extraction from VisitRecord objects.

Builds Obsidian topic notes from structured visit data.
The structured data itself comes from LLM vision extraction, not regex.
"""

from __future__ import annotations

import logging

from .models import (
    Keyword,
    KeywordOccurrence,
    KeywordType,
    VisitRecord,
)
from .utils import link_safe, visit_note_link

logger = logging.getLogger(__name__)


def extract_keywords(visits: list[VisitRecord]) -> list[Keyword]:
    """Extract all unique keywords across visits for Obsidian topic notes."""
    keywords_map: dict[str, Keyword] = {}

    for visit in visits:
        link = visit_note_link(
            visit.patient_name, visit.visit_date.isoformat(), visit.source_pdf
        )

        def add(term: str, ktype: KeywordType, detail: str = "") -> None:
            _add_keyword(keywords_map, term, ktype, visit, link, detail)

        # Diseases and TCM patterns from diagnoses
        for diag in visit.tcm_diagnoses + visit.western_diagnoses:
            add(
                diag.name,
                KeywordType.TCM_PATTERN
                if _is_tcm_pattern(diag.name)
                else KeywordType.DISEASE,
            )

        # Symptoms
        for symptom in visit.symptoms:
            add(symptom, KeywordType.SYMPTOM)

        # Herbs (record dosage as the occurrence detail)
        for formula in visit.herbal_formulas:
            for herb in formula.herbs:
                add(herb.name, KeywordType.HERB, detail=herb.dosage)

        # Medications
        for med in visit.medications:
            add(med.name, KeywordType.MEDICATION)
        for med in visit.chinese_patent_medicines:
            add(med.name, KeywordType.MEDICATION)

        # Lab indicators (record value+unit+direction as the occurrence detail)
        for lab in visit.labs:
            term = lab.chinese_name
            if lab.abbreviation:
                term = f"{lab.chinese_name}({lab.abbreviation})"
            detail = f"{lab.value} {lab.unit} {lab.direction or ''}".strip()
            add(term, KeywordType.LAB_INDICATOR, detail=detail)

    return list(keywords_map.values())


def _is_tcm_pattern(name: str) -> bool:
    """Check if a diagnosis name is a TCM pattern (证) vs disease (病)."""
    if name.endswith("证"):
        return True
    return False


def _add_keyword(
    keywords_map: dict[str, Keyword],
    term: str,
    ktype: KeywordType,
    visit: VisitRecord,
    visit_link: str,
    detail: str = "",
) -> None:
    """Add or update a keyword in the map, recording a paired occurrence."""
    if not term:
        return
    term = link_safe(term)
    if term not in keywords_map:
        keywords_map[term] = Keyword(
            term=term,
            type=ktype,
            source_pages=list(visit.source_pages),
        )
    kw = keywords_map[term]
    kw.occurrences.append(
        KeywordOccurrence(
            patient=visit.patient_name,
            visit_link=visit_link,
            visit_date=visit.visit_date.isoformat(),
            detail=detail,
        )
    )
