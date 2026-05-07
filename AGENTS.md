# AGENTS.md — medrec-obsidian

## Purpose

CLI tool that ingests Chinese medical record PDFs into an Obsidian knowledge vault. Uses LLM vision to extract patient demographics, diagnoses (TCM + Western), symptoms, herbal prescriptions, medications, lab results, and builds an interlinked note graph.

## Pipeline

```
PDF → medrec render → PNG images → LLM vision → VisitRecord[] JSON → medrec update → Obsidian vault
```

The Python tool renders pages and writes the vault. The LLM (Claude Code / Codex) does the structured extraction by reading page images.

## Key Modules

| Module | Responsibility |
|--------|---------------|
| `models.py` | Pydantic data models (VisitRecord, Herb, LabResult, Diagnosis, etc.) |
| `config.py` | YAML config loading with sensible defaults |
| `pdf_reader.py` | PyMuPDF page rendering to PNG images |
| `extractor.py` | Keyword and relation extraction from VisitRecords |
| `obsidian_writer.py` | Markdown generation with YAML frontmatter and [[wikilinks]] |
| `graph_builder.py` | Disease-symptom relation notes for Obsidian graph view |
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

# Inspect extracted data
medrec inspect --from-json <json>

# Print JSON schema for extraction
medrec schema
```

## Workflow for LLM agents

See `skills/medical-record-obsidian/SKILL.md` for the complete extraction workflow, JSON schema, and prompt instructions.
