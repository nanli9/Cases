"""Keyword and relation extraction from VisitRecord objects.

Builds Obsidian topic notes and relationship graph from structured visit data.
The structured data itself comes from LLM vision extraction, not regex.
"""

from __future__ import annotations

import logging

from .models import (
    Keyword,
    KeywordType,
    Relation,
    RelationType,
    VisitRecord,
)

logger = logging.getLogger(__name__)


def extract_keywords(visits: list[VisitRecord]) -> list[Keyword]:
    """Extract all unique keywords across visits for Obsidian topic notes."""
    keywords_map: dict[str, Keyword] = {}

    for visit in visits:
        visit_label = f"{visit.patient_name}_{visit.visit_date.isoformat()}"

        # Diseases from diagnoses
        for diag in visit.tcm_diagnoses + visit.western_diagnoses:
            _add_keyword(
                keywords_map,
                diag.name,
                KeywordType.TCM_PATTERN
                if _is_tcm_pattern(diag.name)
                else KeywordType.DISEASE,
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

    # diseases_share_symptom
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

    return _deduplicate_relations(relations)


def _is_tcm_pattern(name: str) -> bool:
    """Check if a diagnosis name is a TCM pattern (证) vs disease (病)."""
    if name.endswith("证"):
        return True
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
            for e in r.evidence:
                if e not in seen[key].evidence:
                    seen[key].evidence.append(e)
        else:
            seen[key] = r
    return list(seen.values())
