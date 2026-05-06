"""Setup script for medrec_obsidian."""

from setuptools import setup, find_packages

setup(
    name="medrec-obsidian",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.1",
        "pydantic>=2.0",
        "PyYAML>=6.0",
        "rich>=13.0",
        "PyMuPDF>=1.24",
        "pdfplumber>=0.11",
        "pytesseract>=0.3.10",
        "Pillow>=10.0",
        "rapidfuzz>=3.0",
    ],
    entry_points={
        "console_scripts": [
            "medrec=medrec_obsidian.cli:main",
        ],
    },
    python_requires=">=3.10",
)
