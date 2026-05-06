# Skill: medical-record-obsidian

## Description

Ingest a Chinese medical record PDF into an Obsidian vault. Extracts patient demographics, TCM and Western diagnoses, symptoms, herbal prescriptions, medications, lab results, and builds an interlinked knowledge graph with Obsidian wikilinks.

**All processing is local.** No cloud services, no LLM APIs, no network requests.

## Prerequisites

The project must be bootstrapped first:
```bash
cd /home/nan/Desktop/cases/medical-record-obsidian
bash bootstrap.sh
```

Or manually:
```bash
python3 -m venv .venv
.venv/bin/pip install -e .
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
```

## When to use this skill

Use when the user asks to:
- Process a medical record PDF
- Ingest medical records into Obsidian
- Extract patient data from a Chinese medical PDF
- Build a medical knowledge graph in Obsidian

## Commands

All commands use the project venv at `/home/nan/Desktop/cases/medical-record-obsidian/.venv/bin/medrec`.

### Inspect a PDF (read-only, always do this first)

```bash
/home/nan/Desktop/cases/medical-record-obsidian/.venv/bin/medrec inspect --pdf <PDF_PATH>
```

Prints detected patients, page grouping, diagnoses, symptoms, medications. No files written.

### Update vault with a PDF

```bash
/home/nan/Desktop/cases/medical-record-obsidian/.venv/bin/medrec update \
    --pdf <PDF_PATH> --vault <VAULT_PATH>
```

### Modes

| Flag | Behavior |
|------|----------|
| (none) | Extract and write immediately |
| `--dry-run` | Print summary of what would be written, no files touched |
| `--review` | Print extracted data, ask for confirmation before writing |
| `--config <path>` | Use custom config YAML |
| `--language zh-CN` | Set OCR language (default: zh-CN) |
| `-v` | Verbose/debug logging |

## Recommended workflow

```bash
MEDREC=/home/nan/Desktop/cases/medical-record-obsidian/.venv/bin/medrec

# 1. Inspect first (always)
$MEDREC inspect --pdf ~/records/门诊病历.pdf

# 2. Dry run to preview
$MEDREC update --pdf ~/records/门诊病历.pdf --vault ~/ObsidianVault --dry-run

# 3. Review and confirm
$MEDREC update --pdf ~/records/门诊病历.pdf --vault ~/ObsidianVault --review

# 4. Direct update (when confident)
$MEDREC update --pdf ~/records/门诊病历.pdf --vault ~/ObsidianVault
```

## Privacy rules — CRITICAL

- Do NOT upload PDFs, extracted text, or patient data to any remote server
- Do NOT call cloud OCR, cloud LLM APIs, or telemetry services
- All processing must run locally
- Source PDFs are copied into the vault's Sources/pdfs/ folder (local only)

## Vault output structure

```
Medical Records/
  Patients/{PatientName}.md
  Visits/{PatientName}/{YYYY-MM-DD}__{pdf_stem}.md
  Topics/
    Diseases/{Name}.md
    Symptoms/{Name}.md
    Medications/{Name}.md
    Herbs/{Name}.md
    Lab Indicators/{Name}.md
    TCM Patterns/{Name}.md
  Relations/{A}__shares_symptom__{B}.md
  Sources/
    manifests/{pdf_stem}.json
    ocr/{pdf_stem}/page_001.txt
    pdfs/{pdf_name}
```
