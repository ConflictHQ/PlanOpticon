"""Mermaid rendering and chart reproduction utilities."""

import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def render_mermaid(mermaid_code: str, output_dir: str | Path, name: str) -> Dict[str, Path]:
    """
    Render mermaid code to SVG and PNG files.

    Writes {name}.mermaid (source), {name}.svg, and {name}.png.
    Uses mermaid-py if available, falls back gracefully.

    Returns dict with keys: mermaid, svg, png (Paths to generated files).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result: Dict[str, Path] = {}

    # Always write source
    mermaid_path = output_dir / f"{name}.mermaid"
    mermaid_path.write_text(mermaid_code)
    result["mermaid"] = mermaid_path

    try:
        import mermaid as mmd
        from mermaid.graph import Graph

        graph = Graph("diagram", mermaid_code)
        rendered = mmd.Mermaid(graph)

        # SVG
        svg_path = output_dir / f"{name}.svg"
        svg_content = rendered.svg_response
        if svg_content:
            if isinstance(svg_content, bytes):
                svg_path.write_bytes(svg_content)
            else:
                svg_path.write_text(svg_content)
            result["svg"] = svg_path

        # PNG
        png_path = output_dir / f"{name}.png"
        png_content = rendered.img_response
        if png_content:
            if isinstance(png_content, bytes):
                png_path.write_bytes(png_content)
            else:
                png_path.write_bytes(png_content.encode() if isinstance(png_content, str) else png_content)
            result["png"] = png_path

    except ImportError:
        logger.warning("mermaid-py not installed, skipping SVG/PNG rendering. Install with: pip install mermaid-py")
    except Exception as e:
        logger.warning(f"Mermaid rendering failed for '{name}': {e}")

    return result


def reproduce_chart(
    chart_data: dict,
    output_dir: str | Path,
    name: str,
) -> Dict[str, Path]:
    """
    Reproduce a chart from extracted data using matplotlib.

    chart_data should contain: labels, values, chart_type (bar/line/pie/scatter).
    Returns dict with keys: svg, png (Paths to generated files).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result: Dict[str, Path] = {}

    labels = chart_data.get("labels", [])
    values = chart_data.get("values", [])
    chart_type = chart_data.get("chart_type", "bar")

    if not labels or not values:
        logger.warning(f"Insufficient chart data for '{name}': missing labels or values")
        return result

    try:
        import matplotlib

        matplotlib.use("Agg")  # Non-interactive backend
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 6))

        if chart_type == "bar":
            ax.bar(labels, values)
        elif chart_type == "line":
            ax.plot(labels, values, marker="o")
        elif chart_type == "pie":
            ax.pie(values, labels=labels, autopct="%1.1f%%")
        elif chart_type == "scatter":
            ax.scatter(range(len(values)), values)
            if labels:
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels, rotation=45, ha="right")
        else:
            ax.bar(labels, values)

        if chart_type != "pie":
            ax.set_xlabel("")
            ax.set_ylabel("")
            plt.xticks(rotation=45, ha="right")

        plt.tight_layout()

        # SVG
        svg_path = output_dir / f"{name}_chart.svg"
        fig.savefig(svg_path, format="svg")
        result["svg"] = svg_path

        # PNG
        png_path = output_dir / f"{name}_chart.png"
        fig.savefig(png_path, format="png", dpi=150)
        result["png"] = png_path

        plt.close(fig)

    except ImportError:
        logger.warning("matplotlib not installed, skipping chart reproduction")
    except Exception as e:
        logger.warning(f"Chart reproduction failed for '{name}': {e}")

    return result
