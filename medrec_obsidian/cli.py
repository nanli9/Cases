"""CLI entry point for medrec: medical record PDF to Obsidian vault."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from .config import Config
from .extractor import extract_all, extract_keywords, extract_relations
from .graph_builder import build_graph
from .models import ProcessingManifest, VisitRecord
from .obsidian_writer import write_vault
from .parser import group_pages, parse_visit
from .pdf_reader import read_pdf
from .utils import today_str

console = Console()
logger = logging.getLogger("medrec")


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
def main(verbose: bool) -> None:
    """medrec: Local-only medical record PDF to Obsidian vault ingestion."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


@main.command()
@click.option("--pdf", required=True, type=click.Path(exists=True), help="Path to the medical record PDF.")
@click.option("--vault", required=True, type=click.Path(), help="Path to the Obsidian vault.")
@click.option("--config", "config_path", type=click.Path(exists=True), default=None, help="Path to config YAML.")
@click.option("--dry-run", is_flag=True, help="Print what would be done without writing files.")
@click.option("--review", is_flag=True, help="Print extracted data for review before writing.")
@click.option("--language", default="zh-CN", help="OCR language (default: zh-CN).")
def update(
    pdf: str,
    vault: str,
    config_path: Optional[str],
    dry_run: bool,
    review: bool,
    language: str,
) -> None:
    """Update an Obsidian vault with data from a medical record PDF."""
    pdf_path = Path(pdf).resolve()
    vault_path = Path(vault).resolve()
    cfg = Config.load(Path(config_path) if config_path else None)
    cfg.language = language

    console.print(f"Processing: [bold]{pdf_path.name}[/bold]")

    # Step 1: Read PDF
    console.print("  Extracting text...", end=" ")
    pages = read_pdf(pdf_path, cfg)
    text_pages = sum(1 for p in pages if p.extraction_method == "text_layer")
    ocr_pages = sum(1 for p in pages if p.extraction_method == "ocr")
    console.print(
        f"{len(pages)} pages (text layer: {text_pages}, OCR: {ocr_pages})"
    )

    # Step 2: Group pages
    console.print("  Grouping pages...", end=" ")
    groups = group_pages(pages, cfg)
    console.print(f"{len(groups)} visit record(s)")

    # Step 3: Parse and extract
    console.print("  Parsing sections...", end=" ")
    visits: list[VisitRecord] = []
    hospital = ""  # auto-detect from first page
    for group in groups:
        visit = parse_visit(group, pdf_path.name, hospital)
        visit = extract_all(visit)
        visits.append(visit)
    console.print(f"{len(visits)} complete")

    # Count unique patients
    patient_names = set(v.patient_name for v in visits)
    console.print(
        f"  Found: [bold]{len(patient_names)}[/bold] patient(s), "
        f"[bold]{len(visits)}[/bold] visit(s)"
    )

    # Step 4: Print summary
    _print_visit_summary(visits)

    # Check for warnings
    all_warnings: list[str] = []
    for v in visits:
        all_warnings.extend(v.warnings)
    if all_warnings:
        console.print(f"\n  [yellow]Warnings ({len(all_warnings)}):[/yellow]")
        for w in all_warnings:
            console.print(f"    - {w}")

    if dry_run:
        console.print("\n  [cyan]DRY RUN -- no files written.[/cyan]")
        return

    if review:
        _print_review(visits)
        if not click.confirm("Proceed with writing to vault?"):
            console.print("  Aborted.")
            return

    # Step 5: Extract keywords and relations
    keywords = extract_keywords(visits)
    relations = extract_relations(visits)

    # Step 6: Build manifest
    manifest = ProcessingManifest(
        source_pdf=pdf_path.name,
        processing_date=today_str(),
        total_pages=len(pages),
        pages_processed=len(pages),
        patients_found=len(patient_names),
        visits_extracted=len(visits),
        duplicate_pages_removed=len(pages) - sum(len(g) for g in groups),
        ocr_pages=ocr_pages,
        text_layer_pages=text_pages,
        warnings=all_warnings,
        patients=sorted(patient_names),
        confidence_by_page={p.pdf_page_index: p.confidence for p in pages},
    )

    # Step 7: Write vault
    console.print(f"\n  Writing to vault: [bold]{vault_path}[/bold]")
    stats = write_vault(
        visits, keywords, vault_path, cfg,
        source_pdf_path=pdf_path,
        manifest=manifest,
    )

    # Step 8: Build graph
    relation_count = build_graph(relations, vault_path, cfg)

    # Print results
    console.print(f"    Visit notes: {stats['visit_notes_created']} created, {stats['visit_notes_updated']} updated")
    console.print(f"    Patient notes: {stats['patient_notes_created']} created, {stats['patient_notes_updated']} updated")
    console.print(f"    Topic notes: {stats['topic_notes_created']} created, {stats['topic_notes_updated']} updated")
    console.print(f"    Relation notes: {relation_count}")
    console.print(f"\n  [green]Done.[/green] {len(all_warnings)} warning(s).")


@main.command()
@click.option("--pdf", required=True, type=click.Path(exists=True), help="Path to the medical record PDF.")
@click.option("--config", "config_path", type=click.Path(exists=True), default=None, help="Path to config YAML.")
@click.option("--language", default="zh-CN", help="OCR language (default: zh-CN).")
def inspect(pdf: str, config_path: Optional[str], language: str) -> None:
    """Inspect a medical record PDF without writing any files.

    Prints detected patients, page grouping, OCR confidence,
    and detected diagnoses/symptoms/medications.
    """
    pdf_path = Path(pdf).resolve()
    cfg = Config.load(Path(config_path) if config_path else None)
    cfg.language = language

    console.print(f"Inspecting: [bold]{pdf_path.name}[/bold]")
    console.print()

    # Read PDF
    pages = read_pdf(pdf_path, cfg)
    text_pages = sum(1 for p in pages if p.extraction_method == "text_layer")
    ocr_pages = sum(1 for p in pages if p.extraction_method == "ocr")

    console.print(f"Pages: {len(pages)} (text layer: {text_pages}, OCR: {ocr_pages})")
    console.print()

    # Page-level confidence
    if ocr_pages > 0:
        console.print("[bold]OCR Confidence Summary:[/bold]")
        table = Table(show_header=True)
        table.add_column("Page")
        table.add_column("Method")
        table.add_column("Confidence")
        for p in pages:
            if p.extraction_method == "ocr":
                conf_str = f"{p.confidence:.2f}"
                table.add_row(str(p.pdf_page_index + 1), "OCR", conf_str)
        console.print(table)
        console.print()

    # Group pages
    groups = group_pages(pages, cfg)
    total_dupes = len(pages) - sum(len(g) for g in groups)

    console.print(f"[bold]Detected {len(groups)} visit record(s) from {len(set(g[0].header.patient_name for g in groups))} patient(s)[/bold]")
    if total_dupes > 0:
        console.print(f"  [yellow]Duplicate pages removed: {total_dupes}[/yellow]")
    console.print()

    # Parse and show per-visit details
    for i, group in enumerate(groups, 1):
        header = group[0].header
        page_nums = [str(p.pdf_page_index + 1) for p in group]

        console.print(f"[bold]Visit {i}: {header.patient_name}[/bold] ({header.sex.value}/{header.age}岁)")
        console.print(f"  Date: {header.visit_date.isoformat()}")
        console.print(f"  Department: {header.department}")
        console.print(f"  Reg#: {header.registration_number}")
        console.print(f"  Pages: {', '.join(page_nums)}")

        # Parse and extract for inspection
        visit = parse_visit(group, pdf_path.name)
        visit = extract_all(visit)

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

        if visit.warnings:
            for w in visit.warnings:
                console.print(f"  [yellow]WARNING: {w}[/yellow]")

        console.print()

    console.print("[green]Inspection complete. No files written.[/green]")


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
