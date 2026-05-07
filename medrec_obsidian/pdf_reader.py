"""PDF page renderer using PyMuPDF.

Renders each page of a PDF to a PNG image for LLM vision extraction.
No OCR, no text parsing — the LLM reads the images directly.
"""

from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def render_pdf_pages(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 200,
) -> list[Path]:
    """Render each page of a PDF to a PNG image.

    Returns a list of output PNG file paths, ordered by page index.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    image_paths: list[Path] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pix = page.get_pixmap(dpi=dpi)
        out_path = output_dir / f"page_{page_idx + 1:03d}.png"
        pix.save(str(out_path))
        image_paths.append(out_path)
        logger.debug("Rendered page %d -> %s", page_idx + 1, out_path)

    doc.close()
    logger.info("Rendered %d pages from %s", len(image_paths), pdf_path.name)
    return image_paths


def get_pdf_page_count(pdf_path: Path) -> int:
    """Return the total number of pages in a PDF."""
    doc = fitz.open(str(pdf_path))
    count = len(doc)
    doc.close()
    return count
