# AGENTS.md — medrec-obsidian

## Purpose

This project is a local-only CLI tool that ingests Chinese medical record PDFs into an Obsidian knowledge vault. It extracts patient demographics, diagnoses (TCM + Western), symptoms, herbal prescriptions, medications, lab results, and builds an interlinked note graph.

## Critical Constraints

1. **LOCAL ONLY**: No network requests. No cloud OCR, no OpenAI/Anthropic/Google/Azure APIs, no telemetry. All processing runs on the local machine.
2. **Privacy**: Never upload PDF content, patient names, or medical data to any remote service.
3. **Deterministic extraction**: All entity extraction uses regex patterns and dictionary matching. No LLM-based extraction.
4. **Provenance**: Every extracted piece of data must trace back to a source PDF, page number, and extraction method with confidence score.
5. **No medical advice**: This tool organizes records. It does not diagnose, recommend treatments, or interpret results.

## Architecture

```
PDF → pdf_reader.py → PageText[] → parser.py → VisitRecord[] → extractor.py → enriched VisitRecord[]
                                                                      ↓
                                                              obsidian_writer.py → Obsidian vault
                                                              graph_builder.py   → Relation notes
```

## Key Modules

| Module | Responsibility |
|--------|---------------|
| `models.py` | Pydantic data models (PatientIdentity, VisitRecord, Keyword, Relation) |
| `config.py` | YAML config loading with sensible defaults |
| `pdf_reader.py` | PyMuPDF text extraction, OCR fallback for image-based pages |
| `ocr.py` | Local pytesseract OCR with chi_sim+eng, image preprocessing |
| `parser.py` | Page grouping by (patient, reg_number, date), dedup, section splitting |
| `extractor.py` | Regex extraction of diagnoses, herbs, meds, labs, symptoms |
| `obsidian_writer.py` | Markdown generation with YAML frontmatter and [[wikilinks]] |
| `graph_builder.py` | Disease-symptom relation notes for Obsidian graph view |
| `cli.py` | Click CLI: `medrec update` and `medrec inspect` |

## Coding Guidelines

- Python 3.10+, type hints on all public functions
- Pydantic v2 for all data models
- No external API calls — verify any new dependency is local-only
- Handle Chinese text (CJK characters, full-width punctuation, mixed encodings)
- Mark unclear OCR output as `[OCR_UNCLEAR]`, unclear handwriting as `[HANDWRITING_UNCLEAR]`
- Test with `pytest tests/`
- Do not hardcode patient names from the example PDF

## CLI Usage

```bash
medrec inspect --pdf <path>                    # read-only inspection
medrec update --pdf <path> --vault <path>      # write to vault
medrec update --pdf <path> --vault <path> --dry-run   # preview without writing
medrec update --pdf <path> --vault <path> --review    # confirm before writing
```
