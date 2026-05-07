"""Graph builder: creates relation notes for disease-symptom and other relationships.

This module builds Obsidian-compatible relation notes that enable the graph view
to show connections between diseases, symptoms, medications, and patients.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from .config import Config
from .models import Relation, RelationType, VisitRecord
from .utils import sanitize_filename, today_str

logger = logging.getLogger(__name__)

# Relation type labels for display
RELATION_LABELS: dict[RelationType, str] = {
    RelationType.DISEASE_HAS_SYMPTOM: "症状",
    RelationType.DISEASE_HAS_INDICATOR: "指标",
    RelationType.DISEASE_TREATED_BY_MEDICATION: "治疗",
    RelationType.DISEASES_SHARE_SYMPTOM: "共同症状",
    RelationType.PATIENT_HAS_DISEASE: "疾病",
    RelationType.PATIENT_HAS_SYMPTOM: "症状",
}


def build_graph(
    relations: list[Relation],
    vault_path: Path,
    config: Config,
) -> int:
    """Write relation notes to the vault.

    Returns the number of relation notes written.
    """
    relations_dir = config.relations_dir(vault_path)
    relations_dir.mkdir(parents=True, exist_ok=True)

    count = 0

    # Only write disease-sharing relations as dedicated notes
    # (other relations are already embedded via wikilinks in visit/patient notes)
    for rel in relations:
        if rel.relation_type == RelationType.DISEASES_SHARE_SYMPTOM:
            _write_relation_note(rel, relations_dir, config)
            count += 1
        elif rel.relation_type == RelationType.DISEASE_HAS_SYMPTOM:
            _write_relation_note(rel, relations_dir, config)
            count += 1

    logger.info("Wrote %d relation notes", count)
    return count


def _write_relation_note(
    rel: Relation, relations_dir: Path, config: Config
) -> None:
    """Write a single relation note."""
    label = RELATION_LABELS.get(rel.relation_type, rel.relation_type.value)
    source_safe = sanitize_filename(rel.source_term)
    target_safe = sanitize_filename(rel.target_term)
    filename = f"{source_safe}__{label}__{target_safe}.md"
    filepath = relations_dir / filename

    tag_prefix = config.obsidian.tag_prefix
    lines: list[str] = []

    frontmatter = {
        "type": "relation",
        "source_term": rel.source_term,
        "target_term": rel.target_term,
        "relation_type": rel.relation_type.value,
        "confidence": rel.confidence,
        "tags": [f"{tag_prefix}/relation"],
    }

    lines.append("---")
    lines.append(
        yaml.dump(
            frontmatter,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ).strip()
    )
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# [[{rel.source_term}]] — {label} — [[{rel.target_term}]]")
    lines.append("")

    # Description
    if rel.relation_type == RelationType.DISEASES_SHARE_SYMPTOM:
        lines.append(
            f"[[{rel.source_term}]] 与 [[{rel.target_term}]] 存在共同症状。"
        )
    elif rel.relation_type == RelationType.DISEASE_HAS_SYMPTOM:
        lines.append(
            f"[[{rel.source_term}]] 表现为 [[{rel.target_term}]]。"
        )
    lines.append("")

    # Evidence
    if rel.evidence:
        lines.append("## 证据")
        lines.append("")
        for ev in rel.evidence:
            lines.append(f"- {ev}")
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")


def rebuild_graph(
    visits: list[VisitRecord],
    vault_path: Path,
    config: Config,
) -> int:
    """Rebuild the entire graph from visit records.

    This is idempotent -- can be re-run after manual edits.
    Imports extract_relations here to avoid circular imports.
    """
    from .extractor import extract_relations

    relations = extract_relations(visits)
    return build_graph(relations, vault_path, config)
