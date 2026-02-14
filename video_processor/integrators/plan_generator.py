"""Plan generation for creating structured markdown output."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

from video_processor.integrators.knowledge_graph import KnowledgeGraph
from video_processor.models import BatchManifest, VideoManifest
from video_processor.providers.manager import ProviderManager

logger = logging.getLogger(__name__)


class PlanGenerator:
    """Generates structured markdown content from extracted data."""

    def __init__(
        self,
        provider_manager: Optional[ProviderManager] = None,
        knowledge_graph: Optional[KnowledgeGraph] = None,
    ):
        self.pm = provider_manager
        self.knowledge_graph = knowledge_graph or KnowledgeGraph(provider_manager=provider_manager)

    def _chat(self, prompt: str, max_tokens: int = 2048, temperature: float = 0.5) -> str:
        if not self.pm:
            return ""
        return self.pm.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def generate_summary(self, transcript: Dict) -> str:
        """Generate summary from transcript."""
        full_text = ""
        if "segments" in transcript:
            for segment in transcript["segments"]:
                if "text" in segment:
                    speaker = f"{segment.get('speaker', 'Speaker')}: " if "speaker" in segment else ""
                    full_text += f"{speaker}{segment['text']}\n\n"

        if not full_text.strip():
            full_text = transcript.get("text", "")

        return self._chat(
            f"Provide a concise 3-5 paragraph summary of this transcript:\n\n{full_text[:6000]}",
            max_tokens=800,
        )

    def generate_markdown(
        self,
        transcript: Dict,
        key_points: List[Dict],
        diagrams: List[Dict],
        knowledge_graph: Dict,
        video_title: Optional[str] = None,
        output_path: Optional[Union[str, Path]] = None,
    ) -> str:
        """Generate markdown report content."""
        summary = self.generate_summary(transcript)
        title = video_title or "Video Analysis Report"

        md = [f"# {title}", "", "## Summary", "", summary, "", "## Key Points", ""]

        for point in key_points:
            p = point.get("point", "") if isinstance(point, dict) else str(point)
            md.append(f"- **{p}**")
            details = point.get("details") if isinstance(point, dict) else None
            if details:
                if isinstance(details, list):
                    for d in details:
                        md.append(f"  - {d}")
                else:
                    md.append(f"  {details}")
            md.append("")

        if diagrams:
            md.append("## Visual Elements")
            md.append("")
            for i, diagram in enumerate(diagrams):
                md.append(f"### Diagram {i + 1}")
                md.append("")
                desc = diagram.get("description", "")
                if desc:
                    md.append(desc)
                    md.append("")
                if diagram.get("image_path"):
                    md.append(f"![Diagram {i + 1}]({diagram['image_path']})")
                    md.append("")
                if diagram.get("mermaid"):
                    md.append("```mermaid")
                    md.append(diagram["mermaid"])
                    md.append("```")
                    md.append("")

        if knowledge_graph and knowledge_graph.get("nodes"):
            md.append("## Knowledge Graph")
            md.append("")
            kg = KnowledgeGraph.from_dict(knowledge_graph)
            mermaid_code = kg.generate_mermaid(max_nodes=25)
            md.append("```mermaid")
            md.append(mermaid_code)
            md.append("```")
            md.append("")

        markdown_content = "\n".join(md)

        if output_path:
            output_path = Path(output_path)
            if not output_path.suffix:
                output_path = output_path.with_suffix(".md")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown_content)
            logger.info(f"Saved markdown to {output_path}")

        return markdown_content

    def generate_batch_summary(
        self,
        manifests: List[VideoManifest],
        kg: Optional[KnowledgeGraph] = None,
        title: str = "Batch Processing Summary",
        output_path: Optional[Union[str, Path]] = None,
    ) -> str:
        """Generate a batch summary across multiple videos."""
        md = [f"# {title}", ""]

        # Overview stats
        total_diagrams = sum(len(m.diagrams) for m in manifests)
        total_kp = sum(len(m.key_points) for m in manifests)
        total_ai = sum(len(m.action_items) for m in manifests)

        md.append("## Overview")
        md.append("")
        md.append(f"- **Videos processed:** {len(manifests)}")
        md.append(f"- **Total diagrams:** {total_diagrams}")
        md.append(f"- **Total key points:** {total_kp}")
        md.append(f"- **Total action items:** {total_ai}")
        md.append("")

        # Per-video summaries
        md.append("## Per-Video Summaries")
        md.append("")
        for m in manifests:
            md.append(f"### {m.video.title}")
            md.append("")
            md.append(f"- Diagrams: {len(m.diagrams)}")
            md.append(f"- Key points: {len(m.key_points)}")
            md.append(f"- Action items: {len(m.action_items)}")
            if m.video.duration_seconds:
                md.append(f"- Duration: {m.video.duration_seconds:.0f}s")
            md.append("")

        # Aggregated action items
        if total_ai > 0:
            md.append("## All Action Items")
            md.append("")
            for m in manifests:
                for ai in m.action_items:
                    line = f"- **{ai.action}**"
                    if ai.assignee:
                        line += f" ({ai.assignee})"
                    if ai.deadline:
                        line += f" — {ai.deadline}"
                    line += f" _{m.video.title}_"
                    md.append(line)
            md.append("")

        # Knowledge graph
        if kg and kg.nodes:
            md.append("## Merged Knowledge Graph")
            md.append("")
            md.append("```mermaid")
            md.append(kg.generate_mermaid(max_nodes=30))
            md.append("```")
            md.append("")

        markdown_content = "\n".join(md)

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown_content)
            logger.info(f"Saved batch summary to {output_path}")

        return markdown_content
