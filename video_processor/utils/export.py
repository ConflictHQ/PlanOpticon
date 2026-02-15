"""Multi-format output orchestration."""

import json
import logging
from pathlib import Path
from typing import Optional

from tqdm import tqdm

from video_processor.models import DiagramResult, VideoManifest
from video_processor.utils.rendering import render_mermaid, reproduce_chart

logger = logging.getLogger(__name__)


def generate_html_report(
    manifest: VideoManifest,
    output_dir: Path,
) -> Optional[Path]:
    """
    Generate a self-contained HTML report with embedded diagrams.

    Reads the markdown analysis and enriches it with rendered SVGs
    and mermaid.js for any unrendered blocks.
    """
    output_dir = Path(output_dir)
    results_dir = output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # Read markdown if available
    md_content = ""
    if manifest.analysis_md:
        md_path = output_dir / manifest.analysis_md
        if md_path.exists():
            md_content = md_path.read_text()

    # Convert markdown to HTML
    try:
        import markdown

        html_body = markdown.markdown(
            md_content,
            extensions=["fenced_code", "tables", "toc"],
        )
    except ImportError:
        logger.warning("markdown library not available, using raw text")
        html_body = f"<pre>{md_content}</pre>"

    # Build sections for key points, action items
    sections = []

    if manifest.key_points:
        kp_html = "<h2>Key Points</h2><ul>"
        for kp in manifest.key_points:
            kp_html += f"<li><strong>{kp.point}</strong>"
            if kp.details:
                kp_html += f" - {kp.details}"
            kp_html += "</li>"
        kp_html += "</ul>"
        sections.append(kp_html)

    if manifest.action_items:
        ai_html = "<h2>Action Items</h2><ul>"
        for ai in manifest.action_items:
            ai_html += f"<li><strong>{ai.action}</strong>"
            if ai.assignee:
                ai_html += f" (assigned to: {ai.assignee})"
            if ai.deadline:
                ai_html += f" — due: {ai.deadline}"
            ai_html += "</li>"
        ai_html += "</ul>"
        sections.append(ai_html)

    # Embed diagram SVGs
    if manifest.diagrams:
        diag_html = "<h2>Diagrams</h2>"
        for i, d in enumerate(manifest.diagrams):
            diag_html += f"<h3>Diagram {i + 1}: {d.description or d.diagram_type.value}</h3>"
            svg_path = output_dir / d.svg_path if d.svg_path else None
            if svg_path and svg_path.exists():
                svg_content = svg_path.read_text()
                diag_html += f'<div class="diagram">{svg_content}</div>'
            elif d.image_path:
                diag_html += f'<img src="{d.image_path}" alt="Diagram {i + 1}" style="max-width:100%">'
            if d.mermaid:
                diag_html += f'<pre class="mermaid">{d.mermaid}</pre>'
        sections.append(diag_html)

    title = manifest.video.title or "PlanOpticon Analysis"
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         max-width: 960px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }}
  h1 {{ color: #1a1a2e; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; }}
  h2 {{ color: #16213e; margin-top: 2em; }}
  h3 {{ color: #0f3460; }}
  pre {{ background: #f5f5f5; padding: 12px; border-radius: 6px; overflow-x: auto; }}
  code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  th {{ background: #f0f0f0; }}
  .diagram {{ margin: 1em 0; text-align: center; }}
  .diagram svg {{ max-width: 100%; height: auto; }}
  img {{ max-width: 100%; height: auto; }}
  ul {{ padding-left: 1.5em; }}
  li {{ margin: 0.3em 0; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{startOnLoad: true}});</script>
</head>
<body>
<h1>{title}</h1>
{html_body}
{"".join(sections)}
</body>
</html>"""

    html_path = results_dir / "analysis.html"
    html_path.write_text(full_html)
    logger.info(f"Generated HTML report: {html_path}")
    return html_path


def generate_pdf_report(html_path: Path, output_path: Path) -> Optional[Path]:
    """
    Convert HTML report to PDF using weasyprint.

    Returns the PDF path or None if weasyprint is not available.
    """
    try:
        from weasyprint import HTML

        HTML(filename=str(html_path)).write_pdf(str(output_path))
        logger.info(f"Generated PDF report: {output_path}")
        return output_path
    except ImportError:
        logger.info("weasyprint not installed, skipping PDF generation")
        return None
    except Exception as e:
        logger.warning(f"PDF generation failed: {e}")
        return None


def export_all_formats(
    output_dir: str | Path,
    manifest: VideoManifest,
) -> VideoManifest:
    """
    Render all diagrams and generate HTML/PDF reports.

    Updates manifest with output file paths and returns it.
    """
    output_dir = Path(output_dir)

    # Render mermaid diagrams to SVG/PNG
    for i, diagram in enumerate(tqdm(manifest.diagrams, desc="Rendering diagrams", unit="diag") if manifest.diagrams else []):
        if diagram.mermaid:
            diagrams_dir = output_dir / "diagrams"
            prefix = f"diagram_{i}"
            paths = render_mermaid(diagram.mermaid, diagrams_dir, prefix)
            if "svg" in paths:
                diagram.svg_path = f"diagrams/{prefix}.svg"
            if "png" in paths:
                diagram.png_path = f"diagrams/{prefix}.png"
            if "mermaid" in paths and not diagram.mermaid_path:
                diagram.mermaid_path = f"diagrams/{prefix}.mermaid"

        # Reproduce charts
        if diagram.chart_data and diagram.diagram_type.value == "chart":
            chart_paths = reproduce_chart(
                diagram.chart_data,
                output_dir / "diagrams",
                f"diagram_{i}",
            )
            if "svg" in chart_paths:
                diagram.svg_path = f"diagrams/diagram_{i}_chart.svg"
            if "png" in chart_paths:
                diagram.png_path = f"diagrams/diagram_{i}_chart.png"

    # Generate HTML report
    html_path = generate_html_report(manifest, output_dir)
    if html_path:
        manifest.analysis_html = str(html_path.relative_to(output_dir))

    # Generate PDF from HTML
    if html_path:
        pdf_path = output_dir / "results" / "analysis.pdf"
        result = generate_pdf_report(html_path, pdf_path)
        if result:
            manifest.analysis_pdf = str(pdf_path.relative_to(output_dir))

    return manifest
