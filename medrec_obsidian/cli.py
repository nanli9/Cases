"""CLI entry point for medrec: medical record PDF to Obsidian vault.

Pipeline: PDF → render PNGs → LLM vision extracts JSON → write vault.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click
from pydantic import TypeAdapter
from rich.console import Console
from rich.table import Table

from .config import Config
from .extractor import extract_keywords
from .models import ProcessingManifest, VisitRecord
from .obsidian_writer import write_vault
from .pdf_reader import render_pdf_pages, get_pdf_page_count
from .utils import today_str

console = Console()
logger = logging.getLogger("medrec")

VisitRecordList = TypeAdapter(list[VisitRecord])


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
def main(verbose: bool) -> None:
    """medrec: Medical record PDF to Obsidian vault ingestion via LLM vision."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


@main.command()
@click.option("--pdf", required=True, type=click.Path(exists=True), help="Path to the medical record PDF.")
@click.option("--output-dir", required=True, type=click.Path(), help="Directory to write rendered PNG images.")
@click.option("--dpi", default=200, help="Render DPI (default: 200).")
def render(pdf: str, output_dir: str, dpi: int) -> None:
    """Render PDF pages as PNG images for LLM vision extraction."""
    pdf_path = Path(pdf).resolve()
    out_dir = Path(output_dir).resolve()

    console.print(f"Rendering: [bold]{pdf_path.name}[/bold] → {out_dir}")

    image_paths = render_pdf_pages(pdf_path, out_dir, dpi=dpi)

    console.print(f"  Rendered [bold]{len(image_paths)}[/bold] pages")
    for p in image_paths:
        console.print(f"    {p}")

    console.print(f"\n[green]Done.[/green] Feed these images to an LLM, extract VisitRecord JSON, then run:")
    console.print(f"  medrec update --from-json <extracted.json> --vault <vault_path>")


@main.command()
@click.option("--pdf", type=click.Path(exists=True), default=None, help="Path to the source PDF (for provenance).")
@click.option("--from-json", "json_path", required=True, type=click.Path(exists=True), help="Path to JSON file with extracted VisitRecord[] data.")
@click.option("--vault", required=True, type=click.Path(), help="Path to the Obsidian vault.")
@click.option("--config", "config_path", type=click.Path(exists=True), default=None, help="Path to config YAML.")
@click.option("--dry-run", is_flag=True, help="Print what would be done without writing files.")
@click.option("--review", is_flag=True, help="Print extracted data for review before writing.")
def update(
    pdf: Optional[str],
    json_path: str,
    vault: str,
    config_path: Optional[str],
    dry_run: bool,
    review: bool,
) -> None:
    """Update an Obsidian vault with LLM-extracted visit data."""
    vault_path = Path(vault).resolve()
    cfg = Config.load(Path(config_path) if config_path else None)

    # Load visit records from JSON
    json_file = Path(json_path).resolve()
    console.print(f"Loading visits from: [bold]{json_file.name}[/bold]")

    raw = json_file.read_text(encoding="utf-8")
    visits = VisitRecordList.validate_json(raw)

    console.print(
        f"  Loaded [bold]{len(visits)}[/bold] visit(s) "
        f"for [bold]{len(set(v.patient_name for v in visits))}[/bold] patient(s)"
    )

    # Print summary
    _print_visit_summary(visits)

    if dry_run:
        console.print("\n  [cyan]DRY RUN -- no files written.[/cyan]")
        return

    if review:
        _print_review(visits)
        if not click.confirm("Proceed with writing to vault?"):
            console.print("  Aborted.")
            return

    # Extract keywords
    keywords = extract_keywords(visits)

    # Build manifest
    pdf_path = Path(pdf).resolve() if pdf else None
    total_pages = get_pdf_page_count(pdf_path) if pdf_path else 0
    patient_names = sorted(set(v.patient_name for v in visits))

    manifest = ProcessingManifest(
        source_pdf=pdf_path.name if pdf_path else json_file.stem,
        processing_date=today_str(),
        total_pages=total_pages,
        pages_processed=total_pages,
        patients_found=len(patient_names),
        visits_extracted=len(visits),
        patients=patient_names,
    )

    # Write vault
    console.print(f"\n  Writing to vault: [bold]{vault_path}[/bold]")
    stats = write_vault(
        visits, keywords, vault_path, cfg,
        source_pdf_path=pdf_path,
        manifest=manifest,
    )

    # Print results
    console.print(f"    Visit notes: {stats['visit_notes_created']} created, {stats['visit_notes_updated']} updated")
    console.print(f"    Patient notes: {stats['patient_notes_created']} created, {stats['patient_notes_updated']} updated")
    console.print(f"    Topic notes: {stats['topic_notes_created']} created, {stats['topic_notes_updated']} updated")
    console.print(f"    Formula notes: {stats['formula_notes_created']} created, {stats['formula_notes_updated']} updated")
    console.print(f"    Doctor notes: {stats['doctor_notes_created']} created, {stats['doctor_notes_updated']} updated")
    console.print(f"\n  [green]Done.[/green]")


@main.command()
@click.option("--from-json", "json_path", required=True, type=click.Path(exists=True), help="Path to JSON file with VisitRecord[] data.")
def inspect(json_path: str) -> None:
    """Inspect extracted visit data from a JSON file."""
    json_file = Path(json_path).resolve()

    raw = json_file.read_text(encoding="utf-8")
    visits = VisitRecordList.validate_json(raw)

    console.print(f"Inspecting: [bold]{json_file.name}[/bold]")
    console.print(f"  {len(visits)} visit(s) from {len(set(v.patient_name for v in visits))} patient(s)")
    console.print()

    for i, visit in enumerate(visits, 1):
        console.print(f"[bold]Visit {i}: {visit.patient_name}[/bold] ({visit.sex.value}/{visit.age}岁)")
        console.print(f"  Date: {visit.visit_date.isoformat()}")
        console.print(f"  Department: {visit.department}")
        console.print(f"  Reg#: {visit.registration_number}")
        console.print(f"  Pages: {', '.join(str(p + 1) for p in visit.source_pages)}")

        if visit.chief_complaint:
            console.print(f"  Chief complaint: {visit.chief_complaint[:80]}")

        if visit.tcm_diagnoses:
            diags = ", ".join(d.name for d in visit.tcm_diagnoses)
            console.print(f"  TCM diagnoses: {diags}")

        if visit.western_diagnoses:
            diags = ", ".join(d.name for d in visit.western_diagnoses)
            console.print(f"  Western diagnoses: {diags}")

        if visit.symptoms:
            console.print(f"  Symptoms: {', '.join(visit.symptoms[:10])}")

        if visit.medications:
            meds = ", ".join(m.name for m in visit.medications)
            console.print(f"  Medications: {meds}")

        if visit.chinese_patent_medicines:
            meds = ", ".join(m.name for m in visit.chinese_patent_medicines)
            console.print(f"  Patent medicines: {meds}")

        if visit.herbal_formulas:
            for f in visit.herbal_formulas:
                herb_names = ", ".join(h.name for h in f.herbs[:8])
                more = f" (+{len(f.herbs) - 8} more)" if len(f.herbs) > 8 else ""
                console.print(f"  Herbal formula #{f.formula_id}: {herb_names}{more}")

        if visit.labs:
            console.print(f"  Lab results: {len(visit.labs)} items")

        console.print()

    console.print("[green]Inspection complete.[/green]")


@main.command()
def schema() -> None:
    """Print the VisitRecord JSON schema for LLM extraction prompts."""
    schema_json = VisitRecordList.json_schema()
    console.print_json(json.dumps(schema_json, indent=2, ensure_ascii=False))


def _print_visit_summary(visits: list[VisitRecord]) -> None:
    """Print a compact summary table of all visits."""
    console.print()
    table = Table(title="Visit Summary", show_header=True)
    table.add_column("#", style="dim")
    table.add_column("Patient")
    table.add_column("Date")
    table.add_column("Pages")
    table.add_column("TCM Dx")
    table.add_column("Western Dx")
    table.add_column("Herbs")
    table.add_column("Meds")

    for i, v in enumerate(visits, 1):
        pages = f"{len(v.source_pages)}p"
        tcm = ", ".join(d.name for d in v.tcm_diagnoses) or "-"
        western = ", ".join(d.name for d in v.western_diagnoses) or "-"
        herb_count = sum(len(f.herbs) for f in v.herbal_formulas)
        med_count = len(v.medications) + len(v.chinese_patent_medicines)

        table.add_row(
            str(i),
            v.patient_name,
            v.visit_date.isoformat(),
            pages,
            tcm[:30],
            western[:30],
            str(herb_count) if herb_count else "-",
            str(med_count) if med_count else "-",
        )

    console.print(table)


def _print_review(visits: list[VisitRecord]) -> None:
    """Print detailed review of extracted data before writing."""
    console.print("\n[bold]== REVIEW ==[/bold]\n")
    for v in visits:
        console.print(f"[bold]{v.patient_name}[/bold] ({v.visit_date.isoformat()})")
        console.print(f"  Chief complaint: {v.chief_complaint}")

        if v.tcm_diagnoses:
            console.print("  TCM diagnoses:")
            for d in v.tcm_diagnoses:
                q = f" ({d.qualifier})" if d.qualifier else ""
                console.print(f"    {d.index}. {d.name}{q}")

        if v.western_diagnoses:
            console.print("  Western diagnoses:")
            for d in v.western_diagnoses:
                q = f" ({d.qualifier})" if d.qualifier else ""
                console.print(f"    {d.index}. {d.name}{q}")

        if v.symptoms:
            console.print(f"  Symptoms: {', '.join(v.symptoms)}")

        for f in v.herbal_formulas:
            console.print(f"  Herbal formula #{f.formula_id} ({f.dose_count} doses, {len(f.herbs)} herbs)")

        if v.medications:
            console.print(f"  Western meds: {', '.join(m.name for m in v.medications)}")

        if v.chinese_patent_medicines:
            console.print(f"  Patent meds: {', '.join(m.name for m in v.chinese_patent_medicines)}")

        if v.labs:
            console.print(f"  Lab results: {len(v.labs)} items")

        console.print()


if __name__ == "__main__":
    main()
