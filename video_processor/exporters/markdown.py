"""Generate structured markdown documents from knowledge graphs.

No LLM required — pure template-based generation from KG data.
Produces federated, curated notes suitable for Obsidian, Notion,
GitHub, or any markdown-based workflow.
"""

import csv
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _heading(text: str, level: int = 1) -> str:
    return f"{'#' * level} {text}"


def _table(headers: List[str], rows: List[List[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _badge(label: str, value: str) -> str:
    return f"**{label}:** {value}"


# ---------------------------------------------------------------------------
# Individual document generators
# ---------------------------------------------------------------------------


def generate_entity_brief(entity: dict, relationships: list) -> str:
    """Generate a one-pager markdown brief for a single entity."""
    name = entity.get("name", "Untitled")
    etype = entity.get("type", "concept")
    descs = entity.get("descriptions", [])
    occs = entity.get("occurrences", [])

    outgoing = [(r["target"], r["type"]) for r in relationships if r.get("source") == name]
    incoming = [(r["source"], r["type"]) for r in relationships if r.get("target") == name]

    parts = [
        _heading(name),
        "",
        _badge("Type", etype),
        "",
    ]

    if descs:
        parts.append(_heading("Summary", 2))
        parts.append("")
        for d in descs:
            parts.append(f"- {d}")
        parts.append("")

    if outgoing:
        parts.append(_heading("Relates To", 2))
        parts.append("")
        parts.append(_table(["Entity", "Relationship"], [[t, r] for t, r in outgoing]))
        parts.append("")

    if incoming:
        parts.append(_heading("Referenced By", 2))
        parts.append("")
        parts.append(_table(["Entity", "Relationship"], [[s, r] for s, r in incoming]))
        parts.append("")

    if occs:
        parts.append(_heading("Sources", 2))
        parts.append("")
        for occ in occs:
            src = occ.get("source", "unknown")
            ts = occ.get("timestamp", "")
            text = occ.get("text", "")
            line = f"- **{src}**"
            if ts:
                line += f" ({ts})"
            if text:
                line += f" — {text}"
            parts.append(line)
        parts.append("")

    return "\n".join(parts)


def generate_executive_summary(kg_data: dict) -> str:
    """Generate a high-level executive summary from the KG."""
    nodes = kg_data.get("nodes", [])
    rels = kg_data.get("relationships", [])

    by_type: Dict[str, list] = {}
    for n in nodes:
        t = n.get("type", "concept")
        by_type.setdefault(t, []).append(n)

    parts = [
        _heading("Executive Summary"),
        "",
        f"Knowledge base contains **{len(nodes)} entities** "
        f"and **{len(rels)} relationships** across "
        f"**{len(by_type)} categories**.",
        "",
        _heading("Entity Breakdown", 2),
        "",
        _table(
            ["Type", "Count", "Examples"],
            [
                [
                    etype,
                    str(len(elist)),
                    ", ".join(e.get("name", "") for e in elist[:3]),
                ]
                for etype, elist in sorted(by_type.items(), key=lambda x: -len(x[1]))
            ],
        ),
        "",
    ]

    # Top connected entities
    degree: Dict[str, int] = {}
    for r in rels:
        degree[r.get("source", "")] = degree.get(r.get("source", ""), 0) + 1
        degree[r.get("target", "")] = degree.get(r.get("target", ""), 0) + 1

    top = sorted(degree.items(), key=lambda x: -x[1])[:10]
    if top:
        parts.append(_heading("Key Entities (by connections)", 2))
        parts.append("")
        parts.append(
            _table(
                ["Entity", "Connections"],
                [[name, str(deg)] for name, deg in top],
            )
        )
        parts.append("")

    # Relationship type breakdown
    rel_types: Dict[str, int] = {}
    for r in rels:
        rt = r.get("type", "related_to")
        rel_types[rt] = rel_types.get(rt, 0) + 1

    if rel_types:
        parts.append(_heading("Relationship Types", 2))
        parts.append("")
        parts.append(
            _table(
                ["Type", "Count"],
                [[rt, str(c)] for rt, c in sorted(rel_types.items(), key=lambda x: -x[1])],
            )
        )
        parts.append("")

    return "\n".join(parts)


def generate_meeting_notes(kg_data: dict, title: Optional[str] = None) -> str:
    """Generate meeting notes format from KG data."""
    nodes = kg_data.get("nodes", [])
    rels = kg_data.get("relationships", [])
    title = title or "Meeting Notes"

    # Categorize by planning-relevant types
    decisions = [n for n in nodes if n.get("type") in ("decision", "constraint")]
    actions = [n for n in nodes if n.get("type") in ("goal", "feature", "milestone")]
    people = [n for n in nodes if n.get("type") == "person"]
    topics = [n for n in nodes if n.get("type") in ("concept", "technology", "topic")]

    parts = [
        _heading(title),
        "",
        f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]

    if topics:
        parts.append(_heading("Discussion Topics", 2))
        parts.append("")
        for t in topics:
            descs = t.get("descriptions", [])
            desc = descs[0] if descs else ""
            parts.append(f"- **{t['name']}**: {desc}")
        parts.append("")

    if people:
        parts.append(_heading("Participants", 2))
        parts.append("")
        for p in people:
            parts.append(f"- {p['name']}")
        parts.append("")

    if decisions:
        parts.append(_heading("Decisions & Constraints", 2))
        parts.append("")
        for d in decisions:
            descs = d.get("descriptions", [])
            desc = descs[0] if descs else ""
            parts.append(f"- **{d['name']}**: {desc}")
        parts.append("")

    if actions:
        parts.append(_heading("Action Items", 2))
        parts.append("")
        for a in actions:
            descs = a.get("descriptions", [])
            desc = descs[0] if descs else ""
            # Find who it's related to
            owners = [
                r["target"]
                for r in rels
                if r.get("source") == a["name"] and r.get("type") in ("assigned_to", "owned_by")
            ]
            owner_str = f" (@{', '.join(owners)})" if owners else ""
            parts.append(f"- [ ] **{a['name']}**{owner_str}: {desc}")
        parts.append("")

    # Open questions (entities without many relationships)
    degree_map: Dict[str, int] = {}
    for r in rels:
        degree_map[r.get("source", "")] = degree_map.get(r.get("source", ""), 0) + 1
        degree_map[r.get("target", "")] = degree_map.get(r.get("target", ""), 0) + 1

    orphans = [n for n in nodes if degree_map.get(n.get("name", ""), 0) <= 1 and n not in people]
    if orphans:
        parts.append(_heading("Open Questions / Loose Ends", 2))
        parts.append("")
        for o in orphans[:10]:
            parts.append(f"- {o['name']}")
        parts.append("")

    return "\n".join(parts)


def generate_glossary(kg_data: dict) -> str:
    """Generate a glossary/dictionary of all entities."""
    nodes = sorted(kg_data.get("nodes", []), key=lambda n: n.get("name", "").lower())

    parts = [
        _heading("Glossary"),
        "",
    ]

    for node in nodes:
        name = node.get("name", "")
        etype = node.get("type", "concept")
        descs = node.get("descriptions", [])
        desc = descs[0] if descs else "No description available."
        parts.append(f"**{name}** *({etype})*")
        parts.append(f": {desc}")
        parts.append("")

    return "\n".join(parts)


def generate_relationship_map(kg_data: dict) -> str:
    """Generate a relationship map as a markdown document with Mermaid diagram."""
    rels = kg_data.get("relationships", [])
    nodes = kg_data.get("nodes", [])

    parts = [
        _heading("Relationship Map"),
        "",
        f"*{len(nodes)} entities, {len(rels)} relationships*",
        "",
    ]

    # Group by relationship type
    by_type: Dict[str, list] = {}
    for r in rels:
        rt = r.get("type", "related_to")
        by_type.setdefault(rt, []).append(r)

    for rt, rlist in sorted(by_type.items()):
        parts.append(_heading(rt.replace("_", " ").title(), 2))
        parts.append("")
        parts.append(
            _table(
                ["Source", "Target"],
                [[r.get("source", ""), r.get("target", "")] for r in rlist],
            )
        )
        parts.append("")

    # Mermaid diagram (top 20 nodes by degree)
    degree: Dict[str, int] = {}
    for r in rels:
        degree[r.get("source", "")] = degree.get(r.get("source", ""), 0) + 1
        degree[r.get("target", "")] = degree.get(r.get("target", ""), 0) + 1

    top_nodes = {name for name, _ in sorted(degree.items(), key=lambda x: -x[1])[:20]}

    if top_nodes:
        parts.append(_heading("Visual Map", 2))
        parts.append("")
        parts.append("```mermaid")
        parts.append("graph LR")

        def safe(s):
            return "".join(c if c.isalnum() or c == "_" else "_" for c in s)

        seen = set()
        for r in rels:
            src, tgt = r.get("source", ""), r.get("target", "")
            if src in top_nodes and tgt in top_nodes:
                key = (src, tgt)
                if key not in seen:
                    parts.append(
                        f'    {safe(src)}["{src}"] -->|{r.get("type", "")}| {safe(tgt)}["{tgt}"]'
                    )
                    seen.add(key)
        parts.append("```")
        parts.append("")

    return "\n".join(parts)


def generate_status_report(kg_data: dict, title: Optional[str] = None) -> str:
    """Generate a project status report from KG data."""
    nodes = kg_data.get("nodes", [])
    rels = kg_data.get("relationships", [])
    title = title or "Status Report"

    milestones = [n for n in nodes if n.get("type") == "milestone"]
    features = [n for n in nodes if n.get("type") == "feature"]
    risks = [n for n in nodes if n.get("type") in ("risk", "constraint")]
    requirements = [n for n in nodes if n.get("type") == "requirement"]

    parts = [
        _heading(title),
        "",
        f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]

    parts.append(_heading("Overview", 2))
    parts.append("")
    parts.append(f"- **Entities:** {len(nodes)}")
    parts.append(f"- **Relationships:** {len(rels)}")
    parts.append(f"- **Features:** {len(features)}")
    parts.append(f"- **Milestones:** {len(milestones)}")
    parts.append(f"- **Requirements:** {len(requirements)}")
    parts.append(f"- **Risks/Constraints:** {len(risks)}")
    parts.append("")

    if milestones:
        parts.append(_heading("Milestones", 2))
        parts.append("")
        for m in milestones:
            descs = m.get("descriptions", [])
            parts.append(f"- **{m['name']}**: {descs[0] if descs else 'TBD'}")
        parts.append("")

    if features:
        parts.append(_heading("Features", 2))
        parts.append("")
        parts.append(
            _table(
                ["Feature", "Description"],
                [[f["name"], (f.get("descriptions") or [""])[0][:60]] for f in features],
            )
        )
        parts.append("")

    if risks:
        parts.append(_heading("Risks & Constraints", 2))
        parts.append("")
        for r in risks:
            descs = r.get("descriptions", [])
            parts.append(f"- **{r['name']}**: {descs[0] if descs else ''}")
        parts.append("")

    return "\n".join(parts)


def generate_entity_index(kg_data: dict) -> str:
    """Generate a master index of all entities grouped by type."""
    nodes = kg_data.get("nodes", [])

    by_type: Dict[str, list] = {}
    for n in nodes:
        t = n.get("type", "concept")
        by_type.setdefault(t, []).append(n)

    parts = [
        _heading("Entity Index"),
        "",
        f"*{len(nodes)} entities across {len(by_type)} types*",
        "",
    ]

    for etype, elist in sorted(by_type.items()):
        parts.append(_heading(f"{etype.title()} ({len(elist)})", 2))
        parts.append("")
        for e in sorted(elist, key=lambda x: x.get("name", "")):
            descs = e.get("descriptions", [])
            desc = f" — {descs[0]}" if descs else ""
            parts.append(f"- **{e['name']}**{desc}")
        parts.append("")

    return "\n".join(parts)


def generate_csv_export(kg_data: dict) -> str:
    """Generate CSV of entities for spreadsheet import."""
    nodes = kg_data.get("nodes", [])
    rels = kg_data.get("relationships", [])

    # Build adjacency info
    related: Dict[str, list] = {}
    for r in rels:
        src = r.get("source", "")
        tgt = r.get("target", "")
        related.setdefault(src, []).append(tgt)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Type", "Description", "Related To", "Source"])

    for n in sorted(nodes, key=lambda x: x.get("name", "")):
        name = n.get("name", "")
        etype = n.get("type", "")
        descs = n.get("descriptions", [])
        desc = descs[0] if descs else ""
        rels_str = "; ".join(related.get(name, []))
        sources = n.get("occurrences", [])
        src_str = sources[0].get("source", "") if sources else ""
        writer.writerow([name, etype, desc, rels_str, src_str])

    return output.getvalue()


# ---------------------------------------------------------------------------
# Document types registry
# ---------------------------------------------------------------------------

DOCUMENT_TYPES = {
    "summary": ("Executive Summary", generate_executive_summary),
    "meeting-notes": ("Meeting Notes", generate_meeting_notes),
    "glossary": ("Glossary", generate_glossary),
    "relationship-map": ("Relationship Map", generate_relationship_map),
    "status-report": ("Status Report", generate_status_report),
    "entity-index": ("Entity Index", generate_entity_index),
    "csv": ("CSV Export", generate_csv_export),
}


def generate_all(
    kg_data: dict,
    output_dir: Path,
    doc_types: Optional[List[str]] = None,
    title: Optional[str] = None,
) -> List[Path]:
    """Generate multiple document types and write to output directory.

    If doc_types is None, generates all available types.
    Returns list of created file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    types_to_generate = doc_types or list(DOCUMENT_TYPES.keys())
    created = []

    for dtype in types_to_generate:
        if dtype not in DOCUMENT_TYPES:
            logger.warning(f"Unknown document type: {dtype}")
            continue

        label, generator = DOCUMENT_TYPES[dtype]
        try:
            content = generator(kg_data)
            ext = ".csv" if dtype == "csv" else ".md"
            filename = f"{dtype}{ext}"
            path = output_dir / filename
            path.write_text(content, encoding="utf-8")
            created.append(path)
            logger.info(f"Generated {label} → {path}")
        except Exception as e:
            logger.error(f"Failed to generate {label}: {e}")

    # Also generate individual entity briefs
    briefs_dir = output_dir / "entities"
    briefs_dir.mkdir(exist_ok=True)
    rels = kg_data.get("relationships", [])
    for node in kg_data.get("nodes", []):
        name = node.get("name", "")
        if not name:
            continue
        safe = name.replace("/", "-").replace("\\", "-").replace(" ", "-")
        brief = generate_entity_brief(node, rels)
        path = briefs_dir / f"{safe}.md"
        path.write_text(brief, encoding="utf-8")
        created.append(path)

    return created
