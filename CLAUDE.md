# CLAUDE.md — medrec-obsidian

## Project overview

Medical record PDF to Obsidian vault ingestion tool. Renders PDF pages as images, uses LLM vision (Claude Code / Codex) to extract structured data, and generates an interlinked Obsidian knowledge vault.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Running commands

Always use the project venv:
```bash
.venv/bin/medrec render --pdf input/<file>.pdf --output-dir /tmp/medrec_pages
.venv/bin/medrec update --from-json <json> --vault vault/ [--pdf input/<file>.pdf]
.venv/bin/medrec inspect --from-json <json>
.venv/bin/medrec schema
```

## Project layout

```
input/          ← drop PDF files here
vault/          ← Obsidian vault output goes here
medrec_obsidian/ ← Python package source
tests/          ← pytest test suite
skills/         ← LLM agent skill definitions
```

## Running tests

```bash
.venv/bin/pytest tests/ -v
```

## Privacy constraints

- Never upload PDFs, patient names, medical text to any remote service.
- LLM vision extraction happens within the local Claude Code / Codex session.
- No cloud OCR, no telemetry.
- This is for organizing records, not for medical advice.

## Architecture

```
PDF → pdf_reader.py (render PNGs) → LLM vision reads images
  → VisitRecord[] JSON → medrec update --from-json
  → obsidian_writer.py → Obsidian vault files
```

The LLM (Claude Code / Codex) does the extraction — no OCR, no regex parsing.
The Python tool handles rendering and vault writing only.

## Key files

- `medrec_obsidian/models.py` — Pydantic data models (VisitRecord, Herb, LabResult, etc.)
- `medrec_obsidian/pdf_reader.py` — PyMuPDF page rendering to PNG
- `medrec_obsidian/extractor.py` — keyword extraction from VisitRecords (paired occurrences with resolvable visit links)
- `medrec_obsidian/store.py` — cumulative master store of VisitRecords (`records.json`); merge/dedup for `update --append`
- `medrec_obsidian/notes.py` — note writer that preserves manual edits (`## 笔记` sections + filled-in 性味/归经/功效分类 + unknown frontmatter keys)
- `medrec_obsidian/obsidian_writer.py` — Obsidian markdown + YAML frontmatter + wikilinks; builds a cross-link index and writes patient/doctor/visit/formula/topic/MOC notes + graph config (all note writers route through `notes.write_note_preserving`)
- `medrec_obsidian/cli.py` — Click CLI: render, update, inspect, schema
- `skills/medical-record-obsidian/SKILL.md` — Full workflow instructions for LLM agents
