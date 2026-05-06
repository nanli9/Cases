"""Local OCR engine for medical record pages.

Supports pytesseract and PaddleOCR backends.
All processing is strictly local -- no cloud services.
"""

from __future__ import annotations

import io
import logging
import re
from typing import TYPE_CHECKING

from PIL import Image, ImageFilter

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger(__name__)

# Markers for unclear OCR regions
OCR_UNCLEAR = "[OCR_UNCLEAR]"
HANDWRITING_UNCLEAR = "[HANDWRITING_UNCLEAR]"


def ocr_page_image(image_bytes: bytes, config: "Config") -> tuple[str, float]:
    """Run local OCR on a page image.

    Args:
        image_bytes: PNG image bytes of the rendered page.
        config: Application config with OCR settings.

    Returns:
        (extracted_text, mean_confidence) where confidence is 0.0-1.0.
    """
    engine = config.ocr.engine.lower()
    if engine == "paddleocr":
        return _ocr_paddleocr(image_bytes)
    elif engine == "pytesseract":
        return _ocr_pytesseract(image_bytes, config.ocr.languages)
    else:
        logger.warning("Unknown OCR engine '%s', trying paddleocr then pytesseract", engine)
        try:
            return _ocr_paddleocr(image_bytes)
        except Exception:
            return _ocr_pytesseract(image_bytes, config.ocr.languages)


def _ocr_pytesseract(image_bytes: bytes, languages: str) -> tuple[str, float]:
    """OCR using pytesseract (local Tesseract engine)."""
    import pytesseract
    from pytesseract import Output

    image = Image.open(io.BytesIO(image_bytes))

    # Pre-processing: convert to grayscale, sharpen
    image = image.convert("L")
    image = image.filter(ImageFilter.SHARPEN)

    # Run OCR with detailed output for confidence scores
    data = pytesseract.image_to_data(
        image, lang=languages, output_type=Output.DICT
    )

    # Reconstruct text with line breaks, filtering low-confidence words
    lines: dict[int, list[str]] = {}
    confidences: list[float] = []

    for i in range(len(data["text"])):
        conf = int(data["conf"][i])
        word = data["text"][i].strip()
        block_num = data["block_num"][i]
        line_num = data["line_num"][i]

        if not word:
            continue

        line_key = block_num * 10000 + line_num

        if conf < 30:
            word = OCR_UNCLEAR
        elif conf < 60:
            confidences.append(conf / 100.0)
        else:
            confidences.append(conf / 100.0)

        if line_key not in lines:
            lines[line_key] = []
        lines[line_key].append(word)

    # Build text from sorted line keys
    text_parts: list[str] = []
    for key in sorted(lines.keys()):
        line_text = " ".join(lines[key])
        text_parts.append(line_text)

    text = "\n".join(text_parts)
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return text, mean_conf


def _ocr_paddleocr(image_bytes: bytes) -> tuple[str, float]:
    """OCR using PaddleOCR (local mode). Supports v3.5+ API."""
    try:
        import numpy as np
        from paddleocr import PaddleOCR
    except ImportError:
        raise ImportError(
            "PaddleOCR not installed. Install with: pip install paddlepaddle paddleocr"
        )

    image = Image.open(io.BytesIO(image_bytes))
    img_array = np.array(image)

    # PaddleOCR v3.5 API: no use_gpu or show_log params
    ocr = PaddleOCR(lang="ch")
    result = ocr.ocr(img_array)

    if not result or not result[0]:
        return "", 0.0

    # Sort by vertical position (y-coordinate of top-left corner)
    entries: list[tuple[float, float, str, float]] = []
    for line in result[0]:
        box = line[0]
        text = line[1][0]
        conf = line[1][1]
        # Use average y of top-left and top-right as line position
        y_pos = (box[0][1] + box[1][1]) / 2
        x_pos = box[0][0]
        entries.append((y_pos, x_pos, text, conf))

    # Group by approximate line (within 20px = same line)
    entries.sort(key=lambda e: (e[0], e[1]))
    lines_grouped: list[list[tuple[float, str, float]]] = []
    current_line: list[tuple[float, str, float]] = []
    current_y = -100.0

    for y, x, text, conf in entries:
        if abs(y - current_y) > 20:
            if current_line:
                lines_grouped.append(current_line)
            current_line = [(x, text, conf)]
            current_y = y
        else:
            current_line.append((x, text, conf))

    if current_line:
        lines_grouped.append(current_line)

    # Build text: sort each line by x position, join
    text_parts: list[str] = []
    all_confs: list[float] = []
    for line in lines_grouped:
        line.sort(key=lambda e: e[0])  # sort by x position
        line_text = " ".join(e[1] for e in line)
        text_parts.append(line_text)
        all_confs.extend(e[2] for e in line)

    text = "\n".join(text_parts)
    mean_conf = sum(all_confs) / len(all_confs) if all_confs else 0.0

    return text, mean_conf
