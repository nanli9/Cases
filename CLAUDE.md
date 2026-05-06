# CLAUDE.md — medrec-obsidian

## Project overview

Local-only medical record PDF to Obsidian vault ingestion tool. Processes Chinese outpatient medical records (TCM + Western medicine) and generates an interlinked Obsidian knowledge vault.

## Setup

```bash
cd /home/nan/Desktop/cases/medical-record-obsidian
python3 -m venv .venv
.venv/bin/pip install -e .
```

System dependency (required for image-based PDFs):
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
```

## Running commands

Always use the project venv:
```bash
.venv/bin/medrec inspect --pdf <path>
.venv/bin/medrec update --pdf <path> --vault <path>
```

## Running tests

```bash
.venv/bin/pytest tests/ -v
```

## Privacy constraints

- ALL processing is local. No network requests ever.
- Never upload PDFs, patient names, medical text, or OCR output to any remote service.
- No cloud OCR, no LLM APIs (OpenAI, Anthropic, Google, Azure), no telemetry.
- This is for organizing records, not for medical advice.

## Architecture

```
PDF → pdf_reader.py → PageText[] → parser.py → VisitRecord[]
  → extractor.py → enriched VisitRecord[]
  → obsidian_writer.py → Obsidian vault files
  → graph_builder.py → Relation notes
```

All entity extraction is deterministic (regex + dictionary). No LLM-based extraction.

## Key files

- `medrec_obsidian/models.py` — Pydantic data models
- `medrec_obsidian/parser.py` — page grouping, dedup, section splitting
- `medrec_obsidian/extractor.py` — regex-based extraction of diagnoses, herbs, meds, labs
- `medrec_obsidian/obsidian_writer.py` — Obsidian markdown + YAML frontmatter + wikilinks
- `medrec_obsidian/cli.py` — Click CLI entry point
