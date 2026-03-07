"""Skill: Export knowledge graph as structured notes (Obsidian, Notion)."""

import csv
import io
import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    Skill,
    register_skill,
)

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Convert a name to a filesystem-safe filename."""
    return (
        name.replace("/", "-")
        .replace("\\", "-")
        .replace(":", "-")
        .replace('"', "")
        .replace("?", "")
        .replace("*", "")
        .replace("<", "")
        .replace(">", "")
        .replace("|", "")
    )


def _build_indexes(kg_data: dict):
    """Build lookup structures from knowledge graph data.

    Returns (nodes, by_type, node_lookup, outgoing, incoming).
    """
    nodes = kg_data.get("nodes", [])
    relationships = kg_data.get("relationships", [])

    by_type: Dict[str, list] = {}
    node_lookup: Dict[str, dict] = {}
    for node in nodes:
        name = node.get("name", node.get("id", ""))
        ntype = node.get("type", "concept")
        by_type.setdefault(ntype, []).append(node)
        node_lookup[name] = node

    outgoing: Dict[str, list] = {}
    incoming: Dict[str, list] = {}
    for rel in relationships:
        src = rel.get("source", "")
        tgt = rel.get("target", "")
        rtype = rel.get("type", "related_to")
        outgoing.setdefault(src, []).append((tgt, rtype))
        incoming.setdefault(tgt, []).append((src, rtype))

    return nodes, by_type, node_lookup, outgoing, incoming


# ---------------------------------------------------------------------------
# Obsidian export
# ---------------------------------------------------------------------------


def export_to_obsidian(
    kg_data: dict,
    output_dir: Path,
    artifacts: Optional[List[Artifact]] = None,
) -> List[Path]:
    """Export knowledge graph as an Obsidian vault.

    Creates one ``.md`` file per entity with YAML frontmatter and
    ``[[wiki-links]]``, an ``_Index.md`` Map of Content, tag pages per
    entity type, and optional artifact notes.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = artifacts or []
    created: List[Path] = []
    today = date.today().isoformat()

    nodes, by_type, node_lookup, outgoing, incoming = _build_indexes(kg_data)

    # --- Individual entity notes ---
    for node in nodes:
        name = node.get("name", node.get("id", ""))
        if not name:
            continue
        ntype = node.get("type", "concept")
        descs = node.get("descriptions", [])
        aliases = node.get("aliases", [])

        # YAML frontmatter
        tags_yaml = f"  - {ntype}"
        aliases_yaml = ""
        if aliases:
            alias_lines = "\n".join(f"  - {a}" for a in aliases)
            aliases_yaml = f"aliases:\n{alias_lines}\n"

        frontmatter = f"---\ntype: {ntype}\ntags:\n{tags_yaml}\n{aliases_yaml}date: {today}\n---\n"

        parts = [frontmatter, f"# {name}", ""]

        # Descriptions
        if descs:
            for d in descs:
                parts.append(f"{d}")
                parts.append("")

        # Outgoing relationships
        outs = outgoing.get(name, [])
        if outs:
            parts.append("## Relationships")
            parts.append("")
            for tgt, rtype in outs:
                parts.append(f"- **{rtype}**: [[{tgt}]]")
            parts.append("")

        # Incoming relationships
        ins = incoming.get(name, [])
        if ins:
            parts.append("## Referenced by")
            parts.append("")
            for src, rtype in ins:
                parts.append(f"- **{rtype}** from [[{src}]]")
            parts.append("")

        filename = _sanitize_filename(name) + ".md"
        path = output_dir / filename
        path.write_text("\n".join(parts), encoding="utf-8")
        created.append(path)

    # --- Index note (Map of Content) ---
    index_parts = [
        "---",
        "type: index",
        "tags:",
        "  - MOC",
        f"date: {today}",
        "---",
        "",
        "# Index",
        "",
        f"**{len(nodes)}** entities | **{len(kg_data.get('relationships', []))}** relationships",
        "",
    ]

    for etype in sorted(by_type.keys()):
        elist = by_type[etype]
        index_parts.append(f"## {etype.title()}")
        index_parts.append("")
        for node in sorted(elist, key=lambda n: n.get("name", "")):
            name = node.get("name", "")
            index_parts.append(f"- [[{name}]]")
        index_parts.append("")

    if artifacts:
        index_parts.append("## Artifacts")
        index_parts.append("")
        for art in artifacts:
            index_parts.append(f"- [[{art.name}]]")
        index_parts.append("")

    index_path = output_dir / "_Index.md"
    index_path.write_text("\n".join(index_parts), encoding="utf-8")
    created.append(index_path)

    # --- Tag pages (one per entity type) ---
    for etype, elist in sorted(by_type.items()):
        tag_parts = [
            "---",
            "type: tag",
            "tags:",
            f"  - {etype}",
            f"date: {today}",
            "---",
            "",
            f"# {etype.title()}",
            "",
            f"All entities of type **{etype}** ({len(elist)}).",
            "",
        ]
        for node in sorted(elist, key=lambda n: n.get("name", "")):
            name = node.get("name", "")
            descs = node.get("descriptions", [])
            summary = descs[0] if descs else ""
            tag_parts.append(f"- [[{name}]]" + (f" - {summary}" if summary else ""))
        tag_parts.append("")

        tag_filename = f"Tag - {etype.title()}.md"
        tag_path = output_dir / _sanitize_filename(tag_filename)
        tag_path.write_text("\n".join(tag_parts), encoding="utf-8")
        created.append(tag_path)

    # --- Artifact notes ---
    for art in artifacts:
        art_parts = [
            "---",
            "type: artifact",
            f"artifact_type: {art.artifact_type}",
            "tags:",
            "  - artifact",
            f"  - {art.artifact_type}",
            f"date: {today}",
            "---",
            "",
            f"# {art.name}",
            "",
            art.content,
            "",
        ]
        art_filename = _sanitize_filename(art.name) + ".md"
        art_path = output_dir / art_filename
        art_path.write_text("\n".join(art_parts), encoding="utf-8")
        created.append(art_path)

    logger.info("Exported %d Obsidian notes to %s", len(created), output_dir)
    return created


# ---------------------------------------------------------------------------
# Notion-compatible markdown export
# ---------------------------------------------------------------------------


def export_to_notion_md(
    kg_data: dict,
    output_dir: Path,
    artifacts: Optional[List[Artifact]] = None,
) -> List[Path]:
    """Export knowledge graph as Notion-compatible markdown.

    Creates ``.md`` files with Notion-style callout blocks and a
    database-style CSV for bulk import.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = artifacts or []
    created: List[Path] = []

    nodes, by_type, node_lookup, outgoing, incoming = _build_indexes(kg_data)

    # --- Database CSV ---
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["Name", "Type", "Description", "Related To"])

    for node in nodes:
        name = node.get("name", node.get("id", ""))
        ntype = node.get("type", "concept")
        descs = node.get("descriptions", [])
        desc_text = "; ".join(descs[:2]) if descs else ""
        outs = outgoing.get(name, [])
        related = ", ".join(tgt for tgt, _ in outs) if outs else ""
        writer.writerow([name, ntype, desc_text, related])

    csv_path = output_dir / "entities_database.csv"
    csv_path.write_text(csv_buffer.getvalue(), encoding="utf-8")
    created.append(csv_path)

    # --- Individual entity pages ---
    for node in nodes:
        name = node.get("name", node.get("id", ""))
        if not name:
            continue
        ntype = node.get("type", "concept")
        descs = node.get("descriptions", [])

        type_emoji = {
            "person": "person",
            "technology": "computer",
            "organization": "building",
            "concept": "bulb",
            "event": "calendar",
            "location": "round_pushpin",
        }
        emoji = type_emoji.get(ntype, "bulb")

        parts = [
            f"# {name}",
            "",
            f"> :{emoji}: **Type:** {ntype}",
            "",
        ]

        if descs:
            parts.append("## Description")
            parts.append("")
            for d in descs:
                parts.append(f"{d}")
                parts.append("")

        # Properties callout
        properties = node.get("properties", {})
        if properties:
            parts.append("> :memo: **Properties**")
            for k, v in properties.items():
                parts.append(f"> - **{k}:** {v}")
            parts.append("")

        # Outgoing relationships
        outs = outgoing.get(name, [])
        if outs:
            parts.append("## Relationships")
            parts.append("")
            parts.append("| Target | Relationship |")
            parts.append("|--------|-------------|")
            for tgt, rtype in outs:
                parts.append(f"| {tgt} | {rtype} |")
            parts.append("")

        # Incoming relationships
        ins = incoming.get(name, [])
        if ins:
            parts.append("## Referenced by")
            parts.append("")
            parts.append("| Source | Relationship |")
            parts.append("|--------|-------------|")
            for src, rtype in ins:
                parts.append(f"| {src} | {rtype} |")
            parts.append("")

        filename = _sanitize_filename(name) + ".md"
        path = output_dir / filename
        path.write_text("\n".join(parts), encoding="utf-8")
        created.append(path)

    # --- Overview page ---
    overview_parts = [
        "# Knowledge Graph Overview",
        "",
        f"> :bar_chart: **Stats:** {len(nodes)} entities, "
        f"{len(kg_data.get('relationships', []))} relationships",
        "",
        "## Entity Types",
        "",
    ]
    for etype in sorted(by_type.keys()):
        elist = by_type[etype]
        overview_parts.append(f"### {etype.title()} ({len(elist)})")
        overview_parts.append("")
        for node in sorted(elist, key=lambda n: n.get("name", "")):
            name = node.get("name", "")
            overview_parts.append(f"- {name}")
        overview_parts.append("")

    if artifacts:
        overview_parts.append("## Artifacts")
        overview_parts.append("")
        for art in artifacts:
            overview_parts.append(f"- **{art.name}** ({art.artifact_type})")
        overview_parts.append("")

    overview_path = output_dir / "Overview.md"
    overview_path.write_text("\n".join(overview_parts), encoding="utf-8")
    created.append(overview_path)

    # --- Artifact pages ---
    for art in artifacts:
        art_parts = [
            f"# {art.name}",
            "",
            f"> :page_facing_up: **Type:** {art.artifact_type} | **Format:** {art.format}",
            "",
            art.content,
            "",
        ]
        art_filename = _sanitize_filename(art.name) + ".md"
        art_path = output_dir / art_filename
        art_path.write_text("\n".join(art_parts), encoding="utf-8")
        created.append(art_path)

    logger.info("Exported %d Notion markdown files to %s", len(created), output_dir)
    return created


# ---------------------------------------------------------------------------
# Skill class
# ---------------------------------------------------------------------------


class NotesExportSkill(Skill):
    """Export knowledge graph as structured notes (Obsidian, Notion).

    For GitHub wiki export, see the ``wiki_generator`` skill.
    """

    name = "notes_export"
    description = "Export knowledge graph as structured notes (Obsidian, Notion)"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        fmt = kwargs.get("format", "obsidian")
        output_dir = Path(kwargs.get("output_dir", f"notes_export_{fmt}"))
        kg_data = context.knowledge_graph.to_dict()
        artifacts = context.artifacts or []

        if fmt == "notion":
            created = export_to_notion_md(kg_data, output_dir, artifacts=artifacts)
        else:
            created = export_to_obsidian(kg_data, output_dir, artifacts=artifacts)

        file_list = "\n".join(f"- {p.name}" for p in created)
        summary = f"Exported {len(created)} {fmt} notes to `{output_dir}`:\n\n{file_list}"

        return Artifact(
            name=f"Notes Export ({fmt.title()})",
            content=summary,
            artifact_type="notes_export",
            format="markdown",
            metadata={
                "output_dir": str(output_dir),
                "format": fmt,
                "file_count": len(created),
                "files": [str(p) for p in created],
            },
        )


register_skill(NotesExportSkill())
