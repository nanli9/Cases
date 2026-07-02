"""CLI-level tests for the four medrec commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from medrec_obsidian.cli import main
from .vault_audit import find_broken_links


def test_schema_outputs_valid_json():
    result = CliRunner().invoke(main, ["schema"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, dict)


def test_render_command(make_pdf, tmp_path):
    pdf = make_pdf(pages=3)
    out = tmp_path / "pages"
    result = CliRunner().invoke(
        main, ["render", "--pdf", str(pdf), "--output-dir", str(out), "--dpi", "100"]
    )
    assert result.exit_code == 0, result.output
    assert len(list(out.glob("*.png"))) == 3


def test_inspect_command(sample_visits_json_file):
    result = CliRunner().invoke(main, ["inspect", "--from-json", str(sample_visits_json_file)])
    assert result.exit_code == 0, result.output
    assert "张三" in result.output
    assert "李四" in result.output


def test_update_dry_run_writes_nothing(sample_visits_json_file, tmp_path):
    vault = tmp_path / "vault"
    result = CliRunner().invoke(
        main,
        ["update", "--from-json", str(sample_visits_json_file), "--vault", str(vault), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert not (vault / "Medical Records").exists()


def test_update_builds_clean_vault(sample_visits_json_file, tmp_path):
    vault = tmp_path / "vault"
    result = CliRunner().invoke(
        main,
        ["update", "--from-json", str(sample_visits_json_file), "--vault", str(vault)],
    )
    assert result.exit_code == 0, result.output
    root = vault / "Medical Records"
    assert root.is_dir()
    assert find_broken_links(root) == {}


def test_inspect_rejects_missing_file(tmp_path):
    result = CliRunner().invoke(main, ["inspect", "--from-json", str(tmp_path / "nope.json")])
    assert result.exit_code != 0
