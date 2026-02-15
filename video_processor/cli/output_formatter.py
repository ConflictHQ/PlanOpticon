"""Output formatting for PlanOpticon analysis results."""

import html
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class OutputFormatter:
    """Formats and organizes output from video analysis."""

    def __init__(self, output_dir: Union[str, Path]):
        """
        Initialize output formatter.

        Parameters
        ----------
        output_dir : str or Path
            Output directory for formatted content
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def organize_outputs(
        self,
        markdown_path: Union[str, Path],
        knowledge_graph_path: Union[str, Path],
        diagrams: List[Dict],
        frames_dir: Optional[Union[str, Path]] = None,
        transcript_path: Optional[Union[str, Path]] = None,
    ) -> Dict:
        """
        Organize outputs into a consistent structure.

        Parameters
        ----------
        markdown_path : str or Path
            Path to markdown analysis
        knowledge_graph_path : str or Path
            Path to knowledge graph JSON
        diagrams : list
            List of diagram analysis results
        frames_dir : str or Path, optional
            Directory with extracted frames
        transcript_path : str or Path, optional
            Path to transcript file

        Returns
        -------
        dict
            Dictionary with organized output paths
        """
        # Create output structure
        md_dir = self.output_dir / "markdown"
        diagrams_dir = self.output_dir / "diagrams"
        data_dir = self.output_dir / "data"

        md_dir.mkdir(exist_ok=True)
        diagrams_dir.mkdir(exist_ok=True)
        data_dir.mkdir(exist_ok=True)

        # Copy markdown file
        markdown_path = Path(markdown_path)
        md_output = md_dir / markdown_path.name
        shutil.copy2(markdown_path, md_output)

        # Copy knowledge graph
        kg_path = Path(knowledge_graph_path)
        kg_output = data_dir / kg_path.name
        shutil.copy2(kg_path, kg_output)

        # Copy diagram images if available
        diagram_images = []
        for diagram in diagrams:
            if "image_path" in diagram and diagram["image_path"]:
                img_path = Path(diagram["image_path"])
                if img_path.exists():
                    img_output = diagrams_dir / img_path.name
                    shutil.copy2(img_path, img_output)
                    diagram_images.append(str(img_output))

        # Copy transcript if provided
        transcript_output = None
        if transcript_path:
            transcript_path = Path(transcript_path)
            if transcript_path.exists():
                transcript_output = data_dir / transcript_path.name
                shutil.copy2(transcript_path, transcript_output)

        # Copy selected frames if provided
        frame_outputs = []
        if frames_dir:
            frames_dir = Path(frames_dir)
            if frames_dir.exists():
                frames_output_dir = self.output_dir / "frames"
                frames_output_dir.mkdir(exist_ok=True)

                # Copy a limited number of representative frames
                frame_files = sorted(list(frames_dir.glob("*.jpg")))
                max_frames = min(10, len(frame_files))
                step = max(1, len(frame_files) // max_frames)

                for i in range(0, len(frame_files), step):
                    if len(frame_outputs) >= max_frames:
                        break

                    frame = frame_files[i]
                    frame_output = frames_output_dir / frame.name
                    shutil.copy2(frame, frame_output)
                    frame_outputs.append(str(frame_output))

        # Return organized paths
        return {
            "markdown": str(md_output),
            "knowledge_graph": str(kg_output),
            "diagram_images": diagram_images,
            "frames": frame_outputs,
            "transcript": str(transcript_output) if transcript_output else None,
        }

    def create_html_index(self, outputs: Dict) -> Path:
        """
        Create HTML index page for outputs.

        Parameters
        ----------
        outputs : dict
            Dictionary with organized output paths

        Returns
        -------
        Path
            Path to HTML index
        """
        esc = html.escape

        # Simple HTML index template
        lines = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "    <title>PlanOpticon Analysis Results</title>",
            "    <style>",
            "        body { font-family: Arial, sans-serif;"
            "              margin: 0; padding: 20px; line-height: 1.6; }",
            "        .container { max-width: 1200px; margin: 0 auto; }",
            "        h1 { color: #333; }",
            "        h2 { color: #555; margin-top: 30px; }",
            "        .section { margin-bottom: 30px; }",
            "        .files { display: flex; flex-wrap: wrap; }",
            "        .file-item { margin: 10px; text-align: center; }",
            "        .file-item img { max-width: 200px; max-height: 150px; object-fit: contain; }",
            "        .file-name { margin-top: 5px; font-size: 0.9em; }",
            "        a { color: #0066cc; text-decoration: none; }",
            "        a:hover { text-decoration: underline; }",
            "    </style>",
            "</head>",
            "<body>",
            "<div class='container'>",
            "    <h1>PlanOpticon Analysis Results</h1>",
            "",
        ]

        # Add markdown section
        if outputs.get("markdown"):
            md_path = Path(outputs["markdown"])
            md_rel = esc(str(md_path.relative_to(self.output_dir)))

            lines.append("    <div class='section'>")
            lines.append("        <h2>Analysis Report</h2>")
            lines.append(f"        <p><a href='{md_rel}' target='_blank'>View Analysis</a></p>")
            lines.append("    </div>")

        # Add diagrams section
        if outputs.get("diagram_images") and len(outputs["diagram_images"]) > 0:
            lines.append("    <div class='section'>")
            lines.append("        <h2>Diagrams</h2>")
            lines.append("        <div class='files'>")

            for img_path in outputs["diagram_images"]:
                img_path = Path(img_path)
                img_rel = esc(str(img_path.relative_to(self.output_dir)))
                img_name = esc(img_path.name)

                lines.append("            <div class='file-item'>")
                lines.append(f"                <a href='{img_rel}' target='_blank'>")
                lines.append(f"                    <img src='{img_rel}' alt='Diagram'>")
                lines.append("                </a>")
                lines.append(f"                <div class='file-name'>{img_name}</div>")
                lines.append("            </div>")

            lines.append("        </div>")
            lines.append("    </div>")

        # Add frames section
        if outputs.get("frames") and len(outputs["frames"]) > 0:
            lines.append("    <div class='section'>")
            lines.append("        <h2>Key Frames</h2>")
            lines.append("        <div class='files'>")

            for frame_path in outputs["frames"]:
                frame_path = Path(frame_path)
                frame_rel = esc(str(frame_path.relative_to(self.output_dir)))
                frame_name = esc(frame_path.name)

                lines.append("            <div class='file-item'>")
                lines.append(f"                <a href='{frame_rel}' target='_blank'>")
                lines.append(f"                    <img src='{frame_rel}' alt='Frame'>")
                lines.append("                </a>")
                lines.append(f"                <div class='file-name'>{frame_name}</div>")
                lines.append("            </div>")

            lines.append("        </div>")
            lines.append("    </div>")

        # Add data files section
        data_files = []
        if outputs.get("knowledge_graph"):
            data_files.append(Path(outputs["knowledge_graph"]))
        if outputs.get("transcript"):
            data_files.append(Path(outputs["transcript"]))

        if data_files:
            lines.append("    <div class='section'>")
            lines.append("        <h2>Data Files</h2>")
            lines.append("        <ul>")

            for data_path in data_files:
                data_rel = esc(str(data_path.relative_to(self.output_dir)))
                data_name = esc(data_path.name)
                lines.append(
                    f"            <li><a href='{data_rel}' target='_blank'>{data_name}</a></li>"
                )

            lines.append("        </ul>")
            lines.append("    </div>")

        # Close HTML
        lines.append("</div>")
        lines.append("</body>")
        lines.append("</html>")

        # Write HTML file
        index_path = self.output_dir / "index.html"
        with open(index_path, "w") as f:
            f.write("\n".join(lines))

        logger.info(f"Created HTML index at {index_path}")
        return index_path
