#!/usr/bin/env bash
# Bootstrap script for medrec-obsidian
# Sets up the Python venv and installs dependencies.
# Run: bash bootstrap.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== medrec-obsidian bootstrap ==="

# 1. Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi

# 2. Install Python dependencies
echo "Installing Python dependencies..."
.venv/bin/pip install -e . --quiet

# 3. Check for tesseract
if command -v tesseract &>/dev/null; then
    echo "Tesseract OCR: installed ($(tesseract --version 2>&1 | head -1))"
    # Check for Chinese language pack
    if tesseract --list-langs 2>&1 | grep -q "chi_sim"; then
        echo "Chinese (Simplified) language pack: installed"
    else
        echo "WARNING: Chinese (Simplified) language pack not installed."
        echo "  Install with: sudo apt-get install tesseract-ocr-chi-sim"
    fi
else
    echo ""
    echo "WARNING: Tesseract OCR is not installed."
    echo "  Tesseract is required for image-based PDFs (most scanned records)."
    echo "  Install with:"
    echo "    Ubuntu/Debian: sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng"
    echo "    macOS:         brew install tesseract tesseract-lang"
    echo ""
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Usage:"
echo "  .venv/bin/medrec inspect --pdf <path>                     # inspect a PDF"
echo "  .venv/bin/medrec update --pdf <path> --vault <vault_path> # ingest into vault"
echo ""
echo "Run tests:"
echo "  .venv/bin/pytest tests/ -v"
