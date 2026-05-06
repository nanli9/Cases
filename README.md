# medrec-obsidian

Local-only medical record PDF to Obsidian vault ingestion tool.

Processes Chinese medical record PDFs (outpatient records with TCM + Western medicine diagnoses) and generates an interlinked Obsidian knowledge vault with patient notes, visit records, disease/symptom/herb topic notes, and a relationship graph.

## Privacy

**All processing is strictly local.** No data is sent to any cloud service, OCR API, or LLM endpoint. PDFs, extracted text, and generated notes stay on your machine.

## Installation

```bash
cd medical-record-obsidian
pip install -e .
```

System dependencies for OCR fallback (only needed if PDF lacks a text layer):

```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng

# macOS
brew install tesseract tesseract-lang
```

## Usage

### Inspect a PDF (read-only)

```bash
medrec inspect --pdf /path/to/medical-record.pdf
```

Prints detected patients, page grouping, diagnoses, symptoms, medications. No files are written.

### Update an Obsidian vault

```bash
medrec update --pdf /path/to/record.pdf --vault /path/to/ObsidianVault
```

Options:
- `--dry-run` — print what would be written without touching the vault
- `--review` — print extracted data for confirmation before writing
- `--config path/to/config.yml` — custom configuration
- `--language zh-CN` — OCR language (default: zh-CN)
- `-v` / `--verbose` — enable debug logging

### Vault structure

```
Medical Records/
  Patients/           — one note per patient
  Visits/             — per-patient subdirectories with per-visit notes
  Topics/
    Diseases/         — disease/diagnosis topic notes
    Symptoms/         — symptom topic notes
    Medications/      — medication topic notes
    Herbs/            — herb topic notes
    Lab Indicators/   — lab result topic notes
    TCM Patterns/     — TCM pattern/证 topic notes
  Relations/          — disease-symptom relationship notes
  Sources/
    manifests/        — JSON processing manifests
    ocr/              — per-page extracted text
    pdfs/             — copy of source PDFs
```

## Configuration

Copy `config.example.yml` to `config.yml` and adjust as needed.

## Testing

```bash
pip install -e ".[dev]"
pytest tests/
```

## Architecture

- **pdf_reader.py** — PyMuPDF text extraction with pytesseract OCR fallback
- **parser.py** — page grouping by patient/date, deduplication, section splitting
- **extractor.py** — deterministic regex + dictionary keyword extraction (no LLM)
- **obsidian_writer.py** — Obsidian markdown generation with YAML frontmatter and wikilinks
- **graph_builder.py** — relationship graph note generation
- **models.py** — Pydantic data models for all structured data
- **cli.py** — Click CLI with `update` and `inspect` commands
