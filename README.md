# medrec-obsidian

Local-only medical record PDF to Obsidian vault ingestion tool.

Processes Chinese medical record PDFs (outpatient records with TCM + Western medicine diagnoses) and generates an interlinked Obsidian knowledge vault with patient notes, visit records, and disease/symptom/herb topic notes.

## Privacy

**All processing is strictly local.** No data is sent to any cloud service. PDFs, extracted data, and generated notes stay on your machine. Vision extraction happens within your local Claude Code / Codex session.

## Installation

```bash
cd medical-record-obsidian
pip install -e .
```

## Usage

### Inspect a PDF (read-only)

```bash
medrec inspect --pdf /path/to/medical-record.pdf
```

Prints detected patients, page grouping, diagnoses, symptoms, medications. No files are written.

### Render pages, then update the vault

The pipeline is: render the PDF to images, have the local LLM read them and emit
`VisitRecord[]` JSON, then write that JSON into the vault.

```bash
# 1. Render PDF pages to PNGs for LLM vision
medrec render --pdf /path/to/record.pdf --output-dir /tmp/medrec_pages

# 2. (LLM reads the images and produces extracted.json)

# 3. Write the extracted data into the vault
medrec update --from-json extracted.json --vault /path/to/ObsidianVault --pdf /path/to/record.pdf
```

`update` options:
- `--append` — accumulate across PDFs (see below)
- `--dry-run` — print what would be written without touching the vault
- `--review` — print extracted data for confirmation before writing
- `--config path/to/config.yml` — custom configuration
- `-v` / `--verbose` — enable debug logging

### Accumulating across multiple PDFs

By default `update` regenerates the aggregate notes (patient / topic / formula /
doctor / MOC) from **only** the JSON you pass in — processing a second PDF on its
own would rewrite those notes to reflect just that file.

Use `--append` to build a cumulative vault instead. Each additional PDF is merged
into a persistent master store at `Medical Records/Sources/records.json` (inside
the gitignored vault, so patient data stays local), and the whole vault is
regenerated from the full union — so aggregate notes correctly accumulate every
patient and visit:

```bash
# First PDF
medrec update --from-json caseA.json --vault /path/to/ObsidianVault --append
# Each additional PDF merges into the store and re-aggregates everything
medrec update --from-json caseB.json --vault /path/to/ObsidianVault --append
```

`update` prints `added / replaced / total` counts. A re-extraction of an already
stored visit (same patient, date, 门诊号 and source PDF) **replaces** the stored
copy rather than duplicating it, so corrections win. Removing a record from the
store is out of scope — stale per-visit files are not deleted.

### Preserving manual edits

Regeneration keeps your hand edits to generated notes:

- A free-text `## 笔记` section is preserved verbatim and re-appended.
- The reference fields `性味` / `归经` / `功效分类` (emitted blank on herb notes as
  a study template) are kept once you fill them in.
- Any frontmatter key the generator does not itself produce is kept.

### Vault structure

```
Medical Records/
  Patients/           — one note per patient
  Doctors/            — one hub note per doctor (their patients + visits)
  Visits/             — per-patient subdirectories with per-visit notes
  Formulas/           — one note per herbal formula (方剂): herbs + 主治 + patient
  Topics/
    Diseases/         — disease/diagnosis topic notes
    Symptoms/         — symptom topic notes
    Medications/      — medication topic notes
    Herbs/            — herb topic notes (formulas, co-herbs, dosages, patterns)
    Lab Indicators/   — lab result topic notes
    TCM Patterns/     — TCM pattern/证 topic notes (symptoms, 治法, formulas)
  Maps/               — per-axis Map-of-Content hubs + a Dataview Dashboard
  Sources/
    pdfs/             — copy of source PDFs
  知识图谱总览.md      — top-level index note
```

### Seeing connections

Topic notes are **bidirectional** and carry structured frontmatter properties, so
the 理法方药 chain (disease → pattern → principle → formula → herb) is traversable
from any node. Notes to explore:

- **Graph view** — color-grouped by entity type (herb / disease / pattern / formula …).
  Groups are written to `.obsidian/graph.json` on each run (your other graph settings
  are preserved).
- **`Maps/Dashboard.md`** — live tables (needs the **Dataview** community plugin).
  Falls back to the static hubs in `知识图谱总览` when Dataview isn't installed.
- **Herb notes** — list every formula the herb appears in, co-prescribed herbs,
  observed dosages, and the patterns it treats. Blank `性味`/`归经`/`功效分类`
  properties are included as a template to fill in while studying.

## Configuration

Copy `config.example.yml` to `config.yml` and adjust as needed.

## Testing

```bash
pip install -e ".[dev]"
pytest tests/
```

## Architecture

- **pdf_reader.py** — PyMuPDF page rendering to PNG (no OCR; the LLM reads the images)
- **extractor.py** — keyword extraction from extracted VisitRecords
- **obsidian_writer.py** — Obsidian markdown generation with YAML frontmatter and wikilinks
- **models.py** — Pydantic data models for all structured data
- **cli.py** — Click CLI: `render`, `update`, `inspect`, `schema`
