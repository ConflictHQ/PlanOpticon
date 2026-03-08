"""Generate PDF reports from knowledge graph data.

Uses reportlab for PDF generation. Falls back gracefully if not installed.
No LLM required — pure template-based generation from KG data.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_styles():
    """Import and configure reportlab styles."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            "KGTitle",
            parent=styles["Title"],
            fontSize=24,
            spaceAfter=20,
            textColor=colors.HexColor("#1a1a2e"),
        )
    )
    styles.add(
        ParagraphStyle(
            "KGHeading2",
            parent=styles["Heading2"],
            fontSize=16,
            spaceBefore=16,
            spaceAfter=8,
            textColor=colors.HexColor("#16213e"),
        )
    )
    styles.add(
        ParagraphStyle(
            "KGBody",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            spaceBefore=4,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "KGBullet",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            leftIndent=20,
            bulletIndent=10,
            spaceBefore=2,
            spaceAfter=2,
        )
    )

    return styles, letter, inch, colors


def _build_entity_table(nodes: List[dict], colors) -> Any:
    """Build a table of entities grouped by type."""
    from reportlab.lib.units import inch
    from reportlab.platypus import Table, TableStyle

    by_type: Dict[str, list] = {}
    for n in nodes:
        t = n.get("type", "concept")
        by_type.setdefault(t, []).append(n)

    data = [["Type", "Count", "Examples"]]
    for etype, elist in sorted(by_type.items(), key=lambda x: -len(x[1])):
        examples = ", ".join(e.get("name", "") for e in elist[:3])
        if len(elist) > 3:
            examples += f" (+{len(elist) - 3} more)"
        data.append([etype.title(), str(len(elist)), examples])

    table = Table(data, colWidths=[1.2 * inch, 0.8 * inch, 4.0 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eaf6")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _build_relationship_table(rels: List[dict], colors, max_rows: int = 30) -> Any:
    """Build a table of relationships."""
    from reportlab.lib.units import inch
    from reportlab.platypus import Table, TableStyle

    data = [["Source", "Relationship", "Target"]]
    for r in rels[:max_rows]:
        data.append([r.get("source", ""), r.get("type", ""), r.get("target", "")])
    if len(rels) > max_rows:
        data.append(["...", f"({len(rels) - max_rows} more)", "..."])

    table = Table(data, colWidths=[2.0 * inch, 2.0 * inch, 2.0 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eaf6")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _build_key_entities_table(rels: List[dict], colors) -> Any:
    """Build a table of top entities by connection count."""
    from reportlab.lib.units import inch
    from reportlab.platypus import Table, TableStyle

    degree: Dict[str, int] = {}
    for r in rels:
        degree[r.get("source", "")] = degree.get(r.get("source", ""), 0) + 1
        degree[r.get("target", "")] = degree.get(r.get("target", ""), 0) + 1

    top = sorted(degree.items(), key=lambda x: -x[1])[:10]
    if not top:
        return None

    data = [["Entity", "Connections"]]
    for name, deg in top:
        data.append([name, str(deg)])

    table = Table(data, colWidths=[4.0 * inch, 1.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eaf6")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def generate_pdf(
    kg_data: dict,
    output_path: Path,
    title: Optional[str] = None,
    diagrams_dir: Optional[Path] = None,
) -> Path:
    """Generate a PDF report from knowledge graph data.

    Args:
        kg_data: Knowledge graph dict with 'nodes' and 'relationships'.
        output_path: Path to write the PDF file.
        title: Optional report title.
        diagrams_dir: Optional directory containing diagram images to embed.

    Returns:
        Path to the generated PDF.

    Raises:
        ImportError: If reportlab is not installed.
    """
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    styles, letter, inch, colors = _get_styles()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    story = []
    nodes = kg_data.get("nodes", [])
    rels = kg_data.get("relationships", [])

    # Title
    report_title = title or "Knowledge Graph Report"
    story.append(Paragraph(report_title, styles["KGTitle"]))
    story.append(
        Paragraph(
            f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} &bull; "
            f"{len(nodes)} entities &bull; {len(rels)} relationships",
            styles["KGBody"],
        )
    )
    story.append(Spacer(1, 20))

    # Entity breakdown
    if nodes:
        story.append(Paragraph("Entity Breakdown", styles["KGHeading2"]))
        story.append(_build_entity_table(nodes, colors))
        story.append(Spacer(1, 12))

    # Key entities
    if rels:
        key_table = _build_key_entities_table(rels, colors)
        if key_table:
            story.append(Paragraph("Key Entities (by connections)", styles["KGHeading2"]))
            story.append(key_table)
            story.append(Spacer(1, 12))

    # Embed diagram images
    if diagrams_dir and diagrams_dir.exists():
        _embed_diagrams(story, styles, diagrams_dir, inch)

    # Relationship table
    if rels:
        story.append(Paragraph("Relationships", styles["KGHeading2"]))
        story.append(_build_relationship_table(rels, colors))
        story.append(Spacer(1, 12))

    # Entity details
    if nodes:
        story.append(Paragraph("Entity Details", styles["KGHeading2"]))
        for node in sorted(nodes, key=lambda n: n.get("name", "")):
            name = node.get("name", "")
            etype = node.get("type", "concept")
            descs = node.get("descriptions", [])
            desc = descs[0] if descs else "No description."
            story.append(Paragraph(f"<b>{name}</b> <i>({etype})</i>: {desc}", styles["KGBullet"]))

    doc.build(story)
    logger.info(f"Generated PDF report: {output_path}")
    return output_path


def _embed_diagrams(story, styles, diagrams_dir: Path, inch):
    """Embed diagram PNG images from a directory."""
    from reportlab.platypus import Image, Paragraph, Spacer

    pngs = sorted(diagrams_dir.glob("*.png"))
    if not pngs:
        return

    story.append(Paragraph("Diagrams", styles["KGHeading2"]))

    for png in pngs:
        try:
            img = Image(str(png), width=5 * inch, height=3.5 * inch)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 8))
        except Exception as e:
            logger.warning(f"Could not embed diagram {png.name}: {e}")
