# Skill: medical-record-obsidian

## Description

Process a Chinese medical record PDF into an interlinked Obsidian vault. Handles everything end-to-end: render pages, extract data via LLM vision, write vault notes.

## When to use

Trigger when the user says anything like:
- "generate the notes for me /path/to/file.pdf"
- "process this medical record"
- "ingest this PDF into obsidian"
- "update the vault with this PDF"

## Vault path rules

- **No vault path given**: use `vault/` in the project root
- **Vault path given**: use it
- **User says "update"**: ask for the vault path if not provided

## Full workflow — execute all steps automatically

```
MEDREC=.venv/bin/medrec
```

### Step 1: Render PDF pages

```bash
$MEDREC render --pdf <PDF_PATH> --output-dir /tmp/medrec_pages_<timestamp>
```

### Step 2: Read each page image with the Read tool

Read every PNG in the output directory. Group pages by patient using the header (patient name, registration number, visit date).

For pages that are duplicates (same patient + reg# + date + identical content), skip them.

### Step 3: Extract structured VisitRecord JSON

For each distinct visit (unique patient + date), extract one JSON object with these fields:

```json
{
  "patient_name": "姓名",
  "sex": "男|女",
  "age": 60,
  "visit_date": "YYYY-MM-DD",
  "hospital": "北京中医药大学东方医院",
  "department": "科室",
  "registration_number": "门诊号",
  "fee_category": "费别",
  "document_id": "DFYY-MZ-XXXXXXXX",
  "doctor": "医生姓名",
  "chief_complaint": "主诉 exact text",
  "present_illness": "现病史 exact text (initial visit only)",
  "follow_ups": [{"date_str": "2026-4-20", "follow_date": "2026-04-20", "text": "复诊内容", "lab_results": []}],
  "chronic_history": "慢性病史",
  "infectious_history": "传染病史",
  "surgical_history": "手术/外伤史",
  "allergy_history": "过敏史",
  "personal_history": "个人史",
  "family_history": "家族史",
  "vital_signs_bp": "120/80",
  "physical_exam": "体格检查",
  "tcm_tongue": "舌象 (from 中医四诊 or inline in 现病史)",
  "tcm_pulse": "脉象 (from 中医四诊 or inline in 现病史)",
  "pattern_basis": "辨证依据",
  "treatment_principle": "治则治法",
  "notes": "注意事项",
  "tcm_diagnoses": [{"index": 1, "name": "眩晕"}, {"index": 2, "name": "气血亏虚证"}],
  "western_diagnoses": [{"index": 1, "name": "眩晕综合征"}],
  "symptoms": ["头晕", "恶心"],
  "herbal_formulas": [{
    "formula_id": "43622340", "dose_count": 7,
    "herbs": [{"name": "姜半夏", "dosage": "12.00g", "dosage_value": 12.0, "dosage_unit": "g"}]
  }],
  "medications": [{"name": "药名", "specification": "规格", "quantity": "数量", "frequency": "频次", "single_dose": "单次剂量", "route": "口服"}],
  "chinese_patent_medicines": [{"name": "中成药名", "specification": "", "quantity": "", "frequency": "", "single_dose": "", "route": "口服"}],
  "labs": [{"chinese_name": "总胆红素", "abbreviation": "TBIL", "value": "32.55", "unit": "μmol/L", "direction": "↑"}],
  "exam_orders": [{"name": "生化（22）", "cost": 360}],
  "source_pdf": "filename.pdf",
  "source_pages": [0, 1, 2],
  "extraction_confidence": 1.0
}
```

Use `qualifier` field on diagnoses for text after `|` or in `[]` brackets (e.g. `{"name": "偏头痛不伴有先兆", "qualifier": "普通偏头痛"}`).

### Step 4: Save JSON and write vault

Save the `VisitRecord[]` array to `/tmp/medrec_extracted_<timestamp>.json`, then:

```bash
$MEDREC update --from-json <JSON_PATH> --vault <VAULT_PATH> --pdf <PDF_PATH>
```

**Accumulating across PDFs:** when adding a new PDF to a vault that already holds
earlier records, pass `--append` so the new visits merge into the cumulative store
(`<vault>/Medical Records/Sources/records.json`) and the whole vault is regenerated
from the full union (otherwise the aggregate notes are rewritten to reflect only
this PDF):

```bash
$MEDREC update --from-json <NEW_JSON_PATH> --vault <VAULT_PATH> --pdf <PDF_PATH> --append
```

Re-running a corrected extraction of an already stored visit (same patient, date,
门诊号, source PDF) replaces it rather than duplicating. Stale per-visit files are
not deleted.

**Manual edits are preserved on regeneration:** a user's free-text `## 笔记`
section and the herb reference fields `性味` / `归经` / `功效分类` survive each
`update` run, so avoid warning the user that regeneration will wipe those.

### Step 5: Report results

Tell the user what was created: number of patients, visits, topic notes, and the vault path.

## Privacy — CRITICAL

- Never upload PDFs, patient data, or extracted text to any remote service
- All processing is local (rendering + vault writing in Python, extraction in the local LLM session)
