"""PDF text extraction with PyMuPDF and OCR fallback."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import click
import fitz  # PyMuPDF

from .config import Config
from .models import PageHeader, PageText, Sex
from .ocr import ocr_page_image
from .utils import chinese_char_ratio, parse_chinese_date

logger = logging.getLogger(__name__)

# OCR artifact marker
OCR_UNCLEAR = "[OCR_UNCLEAR]"


def read_pdf(pdf_path: Path, config: Config) -> list[PageText]:
    """Read a PDF and extract text from each page.

    For each page:
    1. Try text-layer extraction via PyMuPDF.
    2. If quality is too low (insufficient Chinese characters), fall back to OCR.
    3. Parse the page header (patient demographics).

    Returns a list of PageText objects ordered by page index.
    """
    doc = fitz.open(str(pdf_path))
    pages: list[PageText] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text = page.get_text("text")
        method = "text_layer"
        confidence = 1.0

        # Check text quality
        ratio = chinese_char_ratio(text)
        total_chars = len(text.strip())

        if ratio < config.min_chinese_char_ratio or total_chars < 50:
            # Fall back to OCR
            logger.info(
                "Page %d: low text quality (ratio=%.2f, chars=%d), using OCR",
                page_idx + 1,
                ratio,
                total_chars,
            )
            try:
                pix = page.get_pixmap(dpi=config.ocr.dpi)
                img_bytes = pix.tobytes("png")
                text, confidence = ocr_page_image(img_bytes, config)
                method = "ocr"
            except Exception as e:
                error_msg = str(e)
                if "tesseract" in error_msg.lower() or "not found" in error_msg.lower():
                    raise click.ClickException(
                        "This PDF is image-based and requires OCR.\n"
                        "Tesseract is not installed. Install with:\n"
                        "  sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng\n"
                        "Or on macOS: brew install tesseract tesseract-lang"
                    ) from e
                raise

        # Clean OCR artifacts before parsing
        cleaned = _clean_ocr_text(text)

        # Parse header
        header = _parse_page_header(cleaned, page_idx)

        # Extract body text (between header and footer)
        body = _extract_body_text(cleaned)

        pages.append(
            PageText(
                pdf_page_index=page_idx,
                header=header,
                body_text=body,
                extraction_method=method,
                confidence=confidence,
            )
        )

    doc.close()
    return pages


def _clean_ocr_text(text: str) -> str:
    """Clean OCR output text: remove artifact markers, normalize spacing."""
    # Remove [OCR_UNCLEAR] markers
    text = text.replace(OCR_UNCLEAR, "")
    # Remove [HANDWRITING_UNCLEAR] markers
    text = text.replace("[HANDWRITING_UNCLEAR]", "")
    # Collapse multiple spaces into one
    text = re.sub(r"  +", " ", text)
    # Remove spaces around Chinese punctuation
    text = re.sub(r"\s*([：:，。；、])\s*", r"\1", text)
    # Remove spaces between CJK characters (OCR artifact)
    text = re.sub(
        r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])",
        r"\1\2",
        text,
    )
    # Second pass for alternating
    text = re.sub(
        r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])",
        r"\1\2",
        text,
    )
    return text


def _parse_page_header(text: str, page_idx: int) -> PageHeader:
    """Parse patient demographics from the page header text.

    Designed to be robust against OCR noise: flexible spacing,
    multiple regex strategies per field, fallback values.
    """
    # Use first ~500 chars for header parsing (header is at the top)
    header_area = text[:500]

    # Patient name: 2-3 CJK chars after 姓名, stop before 性别
    patient_name = _try_patterns(header_area, [
        r"姓名[：:]\s*([\u4e00-\u9fff]{2,3})(?=性别|性|\s)",
        r"姓名[：:]\s*([\u4e00-\u9fff]{2,3})",
    ]) or ""
    # Strip trailing 性 if captured (common OCR artifact: name runs into 性别)
    if patient_name.endswith("性"):
        patient_name = patient_name[:-1]

    # Sex
    sex_str = _try_patterns(header_area, [
        r"性别[：:]\s*(男|女)",
    ]) or ""

    # Age: digits after 年龄
    age_str = _try_patterns(header_area, [
        r"年龄[：:]\s*(\d+)",
    ]) or "0"

    # Visit date: find YYYY-MM-DD pattern anywhere in header area
    visit_date_str = _try_patterns(header_area, [
        r"就诊时间[：:]\s*(\d{4}-\d{1,2}-\d{1,2})",
        r"(\d{4}-\d{2}-\d{2})",  # fallback: any ISO date
    ]) or ""

    # Registration number: 7+ digits after 门诊号
    reg_number = _try_patterns(header_area, [
        r"门诊号[：:]\s*(\d{5,})",
    ]) or ""

    # Fee category
    fee_category = _try_patterns(header_area, [
        r"费别[：:]\s*([\u4e00-\u9fff]+)",
    ]) or ""

    # Department: look for 脑病X科 or similar pattern
    department = _try_patterns(header_area, [
        r"([\u4e00-\u9fff]+科)\s*[（(]",
        r"(脑病[\u4e00-\u9fff]*科)",
    ]) or ""

    # Document ID
    document_id = _try_patterns(text, [
        r"(DFYY-MZ-\d+)",
    ])

    # Doctor name
    doctor_name = _try_patterns(text, [
        r"医生姓名[：:]([\u4e00-\u9fff]{2,4})",
    ]) or ""

    # Page number: 第X页 (may be garbled, e.g., 第1责)
    page_num_str = _try_patterns(text, [
        r"第\s*(\d+)\s*[页责贞]",
        r"第(\d+)",
    ]) or "1"

    # Parse sex
    sex = Sex.UNKNOWN
    if sex_str == "男":
        sex = Sex.MALE
    elif sex_str == "女":
        sex = Sex.FEMALE

    # Parse visit date
    visit_date = parse_chinese_date(visit_date_str)
    if visit_date is None:
        from datetime import date as date_type
        visit_date = date_type(2000, 1, 1)
        logger.warning(
            "Page %d: could not parse visit date '%s'",
            page_idx + 1,
            visit_date_str,
        )

    return PageHeader(
        patient_name=patient_name,
        sex=sex,
        age=int(age_str) if age_str.isdigit() else 0,
        visit_date=visit_date,
        department=department,
        registration_number=reg_number,
        fee_category=fee_category,
        document_id=document_id,
        doctor_name=doctor_name,
        page_number_in_record=int(page_num_str) if page_num_str.isdigit() else 1,
    )


def _try_patterns(text: str, patterns: list[str]) -> Optional[str]:
    """Try multiple regex patterns in order, returning the first match."""
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip() if m.lastindex else m.group(0).strip()
    return None


def _extract_body_text(text: str) -> str:
    """Extract the body text between the header block and the footer.

    The header ends after the demographics line (费别 or 门诊).
    The footer starts at 医生姓名 line.
    """
    lines = text.split("\n")
    body_lines: list[str] = []
    in_body = False

    for line in lines:
        stripped = line.strip()

        # Detect end of header
        if not in_body:
            # Header ends after line with 费别 or 门诊
            if re.search(r"(费别|门诊$|科\d.*门诊)", stripped):
                in_body = True
                continue
            # Also start body if we see a section marker (even garbled)
            if re.search(
                r"(主\s*诉|现.*病.*史|既.*往.*史|体格检查|生命体征|"
                r"家.*族.*史|过.*敏.*史|个.*人.*史|初步诊断|处\s*置)",
                stripped,
            ):
                in_body = True
                body_lines.append(line)
                continue
            continue

        # Detect footer: 医生姓名 or line with just 第X页
        if re.search(r"医生姓名", stripped):
            break
        # Also stop at DFYY-MZ document ID line if it's the last content
        if re.match(r"^DFYY-MZ-\d+$", stripped):
            break

        body_lines.append(line)

    return "\n".join(body_lines).strip()


def get_pdf_page_count(pdf_path: Path) -> int:
    """Return the total number of pages in a PDF."""
    doc = fitz.open(str(pdf_path))
    count = len(doc)
    doc.close()
    return count
