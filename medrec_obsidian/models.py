"""Pydantic data models for medical record extraction."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Sex(str, Enum):
    MALE = "男"
    FEMALE = "女"
    UNKNOWN = "未知"


class KeywordType(str, Enum):
    DISEASE = "disease"
    SYMPTOM = "symptom"
    MEDICATION = "medication"
    HERB = "herb"
    LAB_INDICATOR = "lab_indicator"
    IMAGING = "imaging"
    PROCEDURE = "procedure"
    TCM_PATTERN = "tcm_pattern"
    OTHER = "other"


class RelationType(str, Enum):
    DISEASE_HAS_SYMPTOM = "disease_has_symptom"
    DISEASE_HAS_INDICATOR = "disease_has_indicator"
    DISEASE_TREATED_BY_MEDICATION = "disease_treated_by_medication"
    DISEASES_SHARE_SYMPTOM = "diseases_share_symptom"
    PATIENT_HAS_DISEASE = "patient_has_disease"
    PATIENT_HAS_SYMPTOM = "patient_has_symptom"


# --- Page-level models ---


class PageHeader(BaseModel):
    """Demographics block extracted from the top of every page."""

    patient_name: str
    sex: Sex
    age: int
    visit_date: date
    department: str
    registration_number: str
    fee_category: str = ""
    document_id: Optional[str] = None
    doctor_name: str = ""
    page_number_in_record: int = 1


class PageText(BaseModel):
    """One page of extracted text with metadata."""

    pdf_page_index: int  # 0-based index in the PDF
    header: PageHeader
    body_text: str  # text below demographics, above footer
    extraction_method: str = "text_layer"  # "text_layer" or "ocr"
    confidence: float = 1.0  # 0.0-1.0


# --- Structured extraction sub-models ---


class Herb(BaseModel):
    """A single herb entry within a formula."""

    name: str
    dosage: str  # e.g. "12.00g"
    dosage_value: float = 0.0
    dosage_unit: str = "g"


class HerbalFormula(BaseModel):
    """A herbal formula prescription."""

    formula_id: str = ""  # e.g. "43622340"
    dose_count: int = 0  # 贴数
    herbs: list[Herb] = Field(default_factory=list)


class WesternMedication(BaseModel):
    """A western medication prescription entry."""

    name: str
    specification: str = ""  # e.g. "(四带20mg*60粒)"
    quantity: str = ""  # e.g. "1.00盒/mg"
    frequency: str = ""  # e.g. "三次/日 (9-15-21)"
    single_dose: str = ""  # e.g. "20(mg)"
    route: str = ""  # e.g. "口服"


class ChinesePatentMedicine(BaseModel):
    """A Chinese patent medicine (中成药) prescription entry."""

    name: str
    specification: str = ""
    quantity: str = ""
    frequency: str = ""
    single_dose: str = ""
    route: str = ""


class LabResult(BaseModel):
    """A laboratory test result."""

    chinese_name: str = ""
    abbreviation: str = ""
    value: str = ""  # string to handle "3+" qualitative values
    unit: str = ""
    direction: Optional[str] = None  # "↑", "↓", or None
    is_starred: bool = False


class ExamOrder(BaseModel):
    """An ordered examination/test."""

    name: str
    cost: Optional[float] = None


class Diagnosis(BaseModel):
    """A single diagnosis entry."""

    index: int = 0  # 1-based
    name: str
    qualifier: Optional[str] = None  # text after | or in []


class FollowUpEntry(BaseModel):
    """A dated follow-up entry within 现病史."""

    date_str: str  # raw date string
    follow_date: Optional[date] = None
    text: str = ""
    lab_results: list[LabResult] = Field(default_factory=list)


# --- Top-level record models ---


class PatientIdentity(BaseModel):
    """Patient identity information."""

    name: str
    sex: Sex = Sex.UNKNOWN
    age: int = 0
    date_of_birth: Optional[date] = None
    registration_number: Optional[str] = None
    insurance_type: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class VisitRecord(BaseModel):
    """One complete visit record for one patient on one date."""

    # Identity
    patient_name: str
    sex: Sex = Sex.UNKNOWN
    age: int = 0
    visit_date: date
    hospital: str = ""
    department: str = ""
    registration_number: str = ""
    fee_category: str = ""
    document_id: Optional[str] = None
    doctor: str = ""

    # Raw section text
    chief_complaint: str = ""
    present_illness: str = ""
    follow_ups: list[FollowUpEntry] = Field(default_factory=list)
    chronic_history: Optional[str] = None
    infectious_history: Optional[str] = None
    surgical_history: Optional[str] = None
    allergy_history: Optional[str] = None
    personal_history: Optional[str] = None
    family_history: Optional[str] = None
    vital_signs_bp: Optional[str] = None
    physical_exam: Optional[str] = None
    tcm_tongue: Optional[str] = None
    tcm_pulse: Optional[str] = None
    pattern_basis: Optional[str] = None
    treatment_principle: Optional[str] = None
    auxiliary_exam: Optional[str] = None
    notes: Optional[str] = None

    # Structured extracted data
    tcm_diagnoses: list[Diagnosis] = Field(default_factory=list)
    western_diagnoses: list[Diagnosis] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    diseases: list[str] = Field(default_factory=list)
    medications: list[WesternMedication] = Field(default_factory=list)
    chinese_patent_medicines: list[ChinesePatentMedicine] = Field(
        default_factory=list
    )
    herbal_formulas: list[HerbalFormula] = Field(default_factory=list)
    herbs: list[str] = Field(default_factory=list)
    labs: list[LabResult] = Field(default_factory=list)
    exam_orders: list[ExamOrder] = Field(default_factory=list)
    imaging: list[str] = Field(default_factory=list)
    procedures: list[str] = Field(default_factory=list)
    prescriptions: list[str] = Field(default_factory=list)

    # Provenance
    raw_text_by_page: dict[int, str] = Field(default_factory=dict)
    source_pdf: str = ""
    source_pages: list[int] = Field(default_factory=list)
    extraction_confidence: float = 1.0
    uncertain_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Keyword(BaseModel):
    """An extracted keyword/entity for Obsidian topic notes."""

    term: str
    type: KeywordType = KeywordType.OTHER
    aliases: list[str] = Field(default_factory=list)
    linked_patients: list[str] = Field(default_factory=list)
    linked_visits: list[str] = Field(default_factory=list)
    evidence_snippets: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)


class Relation(BaseModel):
    """A relationship between two entities."""

    source_term: str
    target_term: str
    relation_type: RelationType
    evidence: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    confidence: float = 1.0


class ProcessingManifest(BaseModel):
    """Manifest for a processed PDF file."""

    source_pdf: str
    processing_date: str
    total_pages: int = 0
    pages_processed: int = 0
    patients_found: int = 0
    visits_extracted: int = 0
    duplicate_pages_removed: int = 0
    ocr_pages: int = 0
    text_layer_pages: int = 0
    warnings: list[str] = Field(default_factory=list)
    patients: list[str] = Field(default_factory=list)
    confidence_by_page: dict[int, float] = Field(default_factory=dict)
