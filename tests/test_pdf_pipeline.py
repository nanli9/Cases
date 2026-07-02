"""End-to-end pipeline tests for ingesting a new PDF.

Priority suite: whenever a new medical-record PDF is processed, these tests
guard the two deterministic halves of the pipeline —
  1. rendering the PDF to page images (pdf_reader), and
  2. building the Obsidian vault from an extraction JSON (obsidian_writer),
     with a full link-integrity audit so no broken wikilinks slip in.

The LLM vision step in the middle is non-deterministic and out of scope; these
tests use synthetic PDFs and a synthetic extraction dataset (no patient data).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from medrec_obsidian.config import Config
from medrec_obsidian.extractor import extract_keywords
from medrec_obsidian.models import VisitRecord
from medrec_obsidian.obsidian_writer import write_vault
from medrec_obsidian.pdf_reader import get_pdf_page_count, render_pdf_pages

from .vault_audit import find_broken_links


class TestRenderNewPdf:
    """Step 1 of the pipeline: a freshly added PDF renders to page images."""

    def test_page_count_matches(self, make_pdf):
        pdf = make_pdf(pages=5)
        assert get_pdf_page_count(pdf) == 5

    def test_renders_one_png_per_page(self, make_pdf, tmp_path):
        pdf = make_pdf(pages=4)
        out = tmp_path / "pages"
        images = render_pdf_pages(pdf, out, dpi=120)
        assert len(images) == 4
        assert all(p.exists() and p.suffix == ".png" for p in images)
        assert all(p.stat().st_size > 0 for p in images)

    def test_output_dir_created_and_sorted(self, make_pdf, tmp_path):
        pdf = make_pdf(pages=3)
        out = tmp_path / "nested" / "pages"  # does not exist yet
        images = render_pdf_pages(pdf, out, dpi=100)
        assert out.is_dir()
        assert images == sorted(images)
        assert [p.name for p in images] == ["page_001.png", "page_002.png", "page_003.png"]

    def test_higher_dpi_produces_larger_images(self, make_pdf, tmp_path):
        pdf = make_pdf(pages=1)
        low = render_pdf_pages(pdf, tmp_path / "lo", dpi=72)[0].stat().st_size
        high = render_pdf_pages(pdf, tmp_path / "hi", dpi=200)[0].stat().st_size
        assert high > low


class TestBuildVaultFromExtraction:
    """Step 2: build the vault from an extraction JSON and validate it."""

    @pytest.fixture
    def built(self, sample_visits, tmp_path):
        config = Config()
        keywords = extract_keywords(sample_visits)
        stats = write_vault(sample_visits, keywords, tmp_path, config)
        return tmp_path / "Medical Records", stats

    def test_note_counts(self, built):
        _, stats = built
        assert stats["visit_notes_created"] == 3
        assert stats["patient_notes_created"] == 2
        assert stats["doctor_notes_created"] == 1
        assert stats["formula_notes_created"] == 3  # F001, F002, F003
        assert stats["topic_notes_created"] > 0

    def test_all_axes_present(self, built):
        root, _ = built
        for sub in ["Patients", "Doctors", "Visits", "Formulas", "Maps"]:
            assert (root / sub).is_dir()
        for topic in ["Diseases", "Symptoms", "Herbs", "TCM Patterns", "Lab Indicators", "Medications"]:
            assert (root / "Topics" / topic).is_dir()
        assert (root / "知识图谱总览.md").exists()
        assert (root / "Maps" / "Dashboard.md").exists()

    def test_no_broken_links(self, built):
        """The whole point: every wikilink in the generated vault resolves."""
        root, _ = built
        broken = find_broken_links(root)
        assert broken == {}, f"unresolved wikilinks: {broken}"

    def test_formula_note_links_herbs_and_diagnosis(self, built):
        root, _ = built
        content = (root / "Formulas" / "方-F001.md").read_text(encoding="utf-8")
        assert "type: formula" in content
        assert "[[桂枝]]" in content and "[[白芍]]" in content
        assert "[[风寒证]]" in content  # 主治

    def test_herb_note_is_bidirectional(self, built):
        root, _ = built
        herb = (root / "Topics" / "Herbs" / "桂枝.md").read_text(encoding="utf-8")
        # 桂枝 appears in all three formulas and next to 甘草.
        assert "[[方-F001]]" in herb
        assert "[[方-F002]]" in herb
        assert "[[方-F003]]" in herb
        assert "[[甘草]]" in herb

    def test_pattern_note_aggregates_symptoms(self, built):
        root, _ = built
        pat = (root / "Topics" / "TCM Patterns" / "风寒证.md").read_text(encoding="utf-8")
        assert "[[头痛]]" in pat
        assert "[[方-F001]]" in pat

    def test_doctor_hub_lists_patients(self, built):
        root, _ = built
        doc = (root / "Doctors" / "李医生.md").read_text(encoding="utf-8")
        assert "[[张三]]" in doc and "[[李四]]" in doc

    def test_link_unsafe_lab_names_are_normalized(self, built):
        root, _ = built
        labs = root / "Topics" / "Lab Indicators"
        # '/' and '#' are replaced with full-width forms so file == link target.
        assert (labs / "谷草／谷丙比值.md").exists()
        assert (labs / "中性粒细胞绝对值(NEUT＃).md").exists()

    def test_rebuild_is_idempotent(self, sample_visits, tmp_path):
        config = Config()
        keywords = extract_keywords(sample_visits)
        write_vault(sample_visits, keywords, tmp_path, config)
        before = _snapshot(tmp_path / "Medical Records")
        write_vault(sample_visits, keywords, tmp_path, config)
        after = _snapshot(tmp_path / "Medical Records")
        assert before == after


def _snapshot(root: Path) -> dict[str, str]:
    """Map every note's relative path to its content, for idempotency checks."""
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in root.rglob("*.md")
        if ".obsidian" not in p.parts
    }
