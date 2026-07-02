# AGENTS.md — medrec-obsidian

## Purpose

CLI tool that ingests Chinese medical record PDFs into an Obsidian knowledge vault. Uses LLM vision to extract patient demographics, diagnoses (TCM + Western), symptoms, herbal prescriptions, medications, lab results, and builds interlinked patient/visit/topic notes.

## Pipeline

```
PDF → medrec render → PNG images → LLM vision → VisitRecord[] JSON → medrec update → Obsidian vault
```

The Python tool renders pages and writes the vault. The LLM (Claude Code / Codex) does the structured extraction by reading page images.

> **Vision required.** The extraction step (reading the rendered PNGs) needs a
> vision-capable model. Under Codex, confirm the active model can read local
> image files; if it cannot, the pipeline cannot proceed past `medrec render`.
> The `render` / `update` / `inspect` / `schema` commands are pure Python and
> run identically regardless of which agent drives them.

## Key Modules

| Module | Responsibility |
|--------|---------------|
| `models.py` | Pydantic data models (VisitRecord, Herb, LabResult, Diagnosis, etc.) |
| `config.py` | YAML config loading with sensible defaults |
| `pdf_reader.py` | PyMuPDF page rendering to PNG images |
| `extractor.py` | Keyword extraction from VisitRecords (paired, resolvable occurrences) |
| `store.py` | Cumulative VisitRecord store (`records.json`); merge/dedup for `update --append` |
| `notes.py` | Note writer preserving manual edits (`## 笔记` + filled-in 性味/归经/功效分类 + user frontmatter keys) |
| `obsidian_writer.py` | Cross-link index + markdown notes (patient/doctor/visit/formula/topic/MOC) with YAML frontmatter and [[wikilinks]] |
| `cli.py` | Click CLI: `render`, `update`, `inspect`, `schema` |

## Coding Guidelines

- Python 3.10+, type hints on all public functions
- Pydantic v2 for all data models
- No OCR, no regex-based text extraction — LLM vision handles this
- Handle Chinese text (CJK characters, full-width punctuation)
- Test with `pytest tests/`

## CLI Usage

```bash
# Render PDF pages as PNGs
medrec render --pdf <path> --output-dir <dir>

# Write to vault from extracted JSON
medrec update --from-json <json> --vault <path> [--pdf <path>]
medrec update --from-json <json> --vault <path> --dry-run
medrec update --from-json <json> --vault <path> --review
# Accumulate across PDFs: merge into records.json, regenerate from the union
medrec update --from-json <json> --vault <path> --append

# Inspect extracted data
medrec inspect --from-json <json>

# Print JSON schema for extraction
medrec schema
```

## Workflow for LLM agents

Execute all steps automatically when the user asks to process / ingest / update a
medical record PDF. `MEDREC=.venv/bin/medrec` (always use the project venv).

**Vault path:** no path given → use `vault/` in the project root; path given → use
it; user says "update" without a path → ask for it.

### Step 1 — Render PDF pages

```bash
$MEDREC render --pdf <PDF_PATH> --output-dir /tmp/medrec_pages_<timestamp>
```

### Step 2 — Read each page image (vision)

Read every PNG in the output directory. Group pages by patient using the header
(patient name, registration number, visit date). Skip duplicate pages (same
patient + reg# + date + identical content).

### Step 3 — Extract one VisitRecord JSON object per distinct visit

One object per unique (patient + date):

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

Use the `qualifier` field on diagnoses for text after `|` or in `[]` brackets
(e.g. `{"name": "偏头痛不伴有先兆", "qualifier": "普通偏头痛"}`).

### Step 4 — Save JSON and write vault

Save the `VisitRecord[]` array to `/tmp/medrec_extracted_<timestamp>.json`, then:

```bash
$MEDREC update --from-json <JSON_PATH> --vault <VAULT_PATH> --pdf <PDF_PATH>
```

**Accumulating across PDFs:** when adding a new PDF to a vault that already holds
earlier records, pass `--append` so the new visits merge into the cumulative store
(`<vault>/Medical Records/Sources/records.json`) and the whole vault is regenerated
from the full union (otherwise the aggregate notes reflect only this PDF):

```bash
$MEDREC update --from-json <NEW_JSON_PATH> --vault <VAULT_PATH> --pdf <PDF_PATH> --append
```

Re-running a corrected extraction of an already stored visit (same patient, date,
门诊号, source PDF) replaces it rather than duplicating; stale per-visit files are
not deleted. Manual edits are preserved on regeneration: a user's free-text
`## 笔记` section and the herb reference fields `性味` / `归经` / `功效分类`
survive each `update` run.

### Step 5 — Report results

Tell the user what was created: number of patients, visits, topic notes, and the
vault path.

The Claude Code skill at `skills/medical-record-obsidian/SKILL.md` mirrors these
instructions and is the source of truth if the two ever diverge.
