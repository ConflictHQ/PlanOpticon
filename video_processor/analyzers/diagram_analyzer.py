"""Diagram analysis using vision model classification and single-pass extraction."""

import json
import logging
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Union

from tqdm import tqdm

from video_processor.models import DiagramResult, DiagramType, ScreenCapture
from video_processor.providers.manager import ProviderManager

logger = logging.getLogger(__name__)

# Classification prompt — returns JSON
_CLASSIFY_PROMPT = """\
Examine this image from a video recording. Your job is to identify ONLY shared content \
— slides, presentations, charts, diagrams, documents, screen shares, whiteboard content, \
architecture drawings, tables, or other structured visual information worth capturing.

IMPORTANT: If the image primarily shows a person, people, webcam feeds, faces, or a \
video conference participant view, return confidence 0.0. We are ONLY interested in \
shared/presented content, NOT people or camera views.

Return ONLY a JSON object (no markdown fences):
{
  "is_diagram": true/false,
  "diagram_type": "flowchart"|"sequence"|"architecture"
    |"whiteboard"|"chart"|"table"|"slide"|"screenshot"|"unknown",
  "confidence": 0.0 to 1.0,
  "content_type": "slide"|"diagram"|"document"|"screen_share"|"whiteboard"|"chart"|"person"|"other",
  "brief_description": "one-sentence description of what you see"
}
"""

# Single-pass analysis prompt — extracts everything in one call
_ANALYSIS_PROMPT = """\
Analyze this diagram/visual content comprehensively. Extract ALL of the
following in a single JSON response (no markdown fences):
{
  "diagram_type": "flowchart"|"sequence"|"architecture"
    |"whiteboard"|"chart"|"table"|"slide"|"screenshot"|"unknown",
  "description": "detailed description of the visual content",
  "text_content": "all visible text, preserving structure",
  "elements": ["list", "of", "identified", "elements/components"],
  "relationships": ["element A -> element B: relationship", ...],
  "mermaid": "mermaid diagram syntax representing this visual (graph LR, sequenceDiagram, etc.)",
  "chart_data": null or {"labels": [...], "values": [...], "chart_type": "bar|line|pie|scatter"}
}

For the mermaid field: generate valid mermaid syntax that best represents the visual structure.
For chart_data: only populate if this is a chart/graph with extractable numeric data.
If any field cannot be determined, use null or empty list.
"""

# Caption prompt for screengrab fallback
_CAPTION_PROMPT = "Briefly describe what this image shows in 1-2 sentences."


def _read_image_bytes(image_path: Union[str, Path]) -> bytes:
    """Read image file as bytes."""
    return Path(image_path).read_bytes()


def _parse_json_response(text: str) -> Optional[dict]:
    """Try to parse JSON from an LLM response, handling markdown fences."""
    if not text:
        return None
    # Strip markdown fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last fence lines
        lines = [line for line in lines if not line.strip().startswith("```")]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                pass
    return None


class DiagramAnalyzer:
    """Vision model-based diagram detection and analysis."""

    def __init__(
        self,
        provider_manager: Optional[ProviderManager] = None,
        confidence_threshold: float = 0.3,
    ):
        self.pm = provider_manager or ProviderManager()
        self.confidence_threshold = confidence_threshold

    def classify_frame(self, image_path: Union[str, Path]) -> dict:
        """
        Classify a single frame using vision model.

        Returns dict with is_diagram, diagram_type, confidence, brief_description.
        """
        image_bytes = _read_image_bytes(image_path)
        raw = self.pm.analyze_image(image_bytes, _CLASSIFY_PROMPT, max_tokens=512)
        result = _parse_json_response(raw)
        if result is None:
            return {
                "is_diagram": False,
                "diagram_type": "unknown",
                "confidence": 0.0,
                "brief_description": "",
            }
        return result

    def analyze_diagram_single_pass(self, image_path: Union[str, Path]) -> dict:
        """
        Full single-pass diagram analysis — description, text, mermaid, chart data.

        Returns parsed dict or empty dict on failure.
        """
        image_bytes = _read_image_bytes(image_path)
        raw = self.pm.analyze_image(image_bytes, _ANALYSIS_PROMPT, max_tokens=4096)
        result = _parse_json_response(raw)
        return result or {}

    def caption_frame(self, image_path: Union[str, Path]) -> str:
        """Get a brief caption for a screengrab fallback."""
        image_bytes = _read_image_bytes(image_path)
        return self.pm.analyze_image(image_bytes, _CAPTION_PROMPT, max_tokens=256)

    def process_frames(
        self,
        frame_paths: List[Union[str, Path]],
        diagrams_dir: Optional[Path] = None,
        captures_dir: Optional[Path] = None,
    ) -> Tuple[List[DiagramResult], List[ScreenCapture]]:
        """
        Process a list of extracted frames: classify, analyze diagrams, screengrab fallback.

        Thresholds:
          - confidence >= 0.7  → full diagram analysis (story 3.2)
          - 0.3 <= confidence < 0.7 → screengrab fallback (story 3.3)
          - confidence < 0.3 → skip

        Returns (diagrams, screen_captures).
        """
        diagrams: List[DiagramResult] = []
        captures: List[ScreenCapture] = []
        diagram_idx = 0
        capture_idx = 0

        for i, fp in enumerate(tqdm(frame_paths, desc="Analyzing frames", unit="frame")):
            fp = Path(fp)
            logger.info(f"Classifying frame {i}/{len(frame_paths)}: {fp.name}")

            try:
                classification = self.classify_frame(fp)
            except Exception as e:
                logger.warning(f"Classification failed for frame {i}: {e}")
                continue

            confidence = float(classification.get("confidence", 0.0))

            if confidence < self.confidence_threshold:
                logger.debug(f"Frame {i}: confidence {confidence:.2f} below threshold, skipping")
                continue

            if confidence >= 0.7:
                # Full diagram analysis
                logger.info(
                    f"Frame {i}: diagram detected (confidence {confidence:.2f}), analyzing..."
                )
                try:
                    analysis = self.analyze_diagram_single_pass(fp)
                except Exception as e:
                    logger.warning(
                        f"Diagram analysis failed for frame {i}: {e}, falling back to screengrab"
                    )
                    analysis = {}

                if not analysis:
                    # Analysis failed — fall back to screengrab
                    capture = self._save_screengrab(fp, i, capture_idx, captures_dir, confidence)
                    captures.append(capture)
                    capture_idx += 1
                    continue

                # Build DiagramResult
                dtype = analysis.get("diagram_type", classification.get("diagram_type", "unknown"))
                try:
                    diagram_type = DiagramType(dtype)
                except ValueError:
                    diagram_type = DiagramType.unknown

                # Normalize relationships: llava sometimes returns dicts instead of strings
                raw_rels = analysis.get("relationships") or []
                relationships = []
                for rel in raw_rels:
                    if isinstance(rel, str):
                        relationships.append(rel)
                    elif isinstance(rel, dict):
                        src = rel.get("source", rel.get("from", "?"))
                        dst = rel.get("destination", rel.get("to", "?"))
                        label = rel.get("label", rel.get("relationship", ""))
                        relationships.append(
                            f"{src} -> {dst}: {label}" if label else f"{src} -> {dst}"
                        )
                    else:
                        relationships.append(str(rel))

                try:
                    dr = DiagramResult(
                        frame_index=i,
                        diagram_type=diagram_type,
                        confidence=confidence,
                        description=analysis.get("description"),
                        text_content=analysis.get("text_content"),
                        elements=analysis.get("elements") or [],
                        relationships=relationships,
                        mermaid=analysis.get("mermaid"),
                        chart_data=analysis.get("chart_data"),
                    )
                except Exception as e:
                    logger.warning(
                        f"DiagramResult validation failed for frame {i}: {e}, "
                        "falling back to screengrab"
                    )
                    capture = self._save_screengrab(fp, i, capture_idx, captures_dir, confidence)
                    captures.append(capture)
                    capture_idx += 1
                    continue

                # Save outputs (story 3.4)
                if diagrams_dir:
                    diagrams_dir.mkdir(parents=True, exist_ok=True)
                    prefix = f"diagram_{diagram_idx}"

                    # Original frame
                    img_dest = diagrams_dir / f"{prefix}.jpg"
                    shutil.copy2(fp, img_dest)
                    dr.image_path = f"diagrams/{prefix}.jpg"

                    # Mermaid source
                    if dr.mermaid:
                        mermaid_dest = diagrams_dir / f"{prefix}.mermaid"
                        mermaid_dest.write_text(dr.mermaid)
                        dr.mermaid_path = f"diagrams/{prefix}.mermaid"

                    # Analysis JSON
                    json_dest = diagrams_dir / f"{prefix}.json"
                    json_dest.write_text(dr.model_dump_json(indent=2))

                diagrams.append(dr)
                diagram_idx += 1

            else:
                # Screengrab fallback (0.3 <= confidence < 0.7)
                logger.info(
                    f"Frame {i}: uncertain (confidence {confidence:.2f}), saving as screengrab"
                )
                capture = self._save_screengrab(fp, i, capture_idx, captures_dir, confidence)
                captures.append(capture)
                capture_idx += 1

        logger.info(
            f"Diagram processing complete: {len(diagrams)} diagrams, {len(captures)} screengrabs"
        )
        return diagrams, captures

    def _save_screengrab(
        self,
        frame_path: Path,
        frame_index: int,
        capture_index: int,
        captures_dir: Optional[Path],
        confidence: float,
    ) -> ScreenCapture:
        """Save a frame as a captioned screengrab."""
        caption = ""
        try:
            caption = self.caption_frame(frame_path)
        except Exception as e:
            logger.warning(f"Caption failed for frame {frame_index}: {e}")

        sc = ScreenCapture(
            frame_index=frame_index,
            caption=caption,
            confidence=confidence,
        )

        if captures_dir:
            captures_dir.mkdir(parents=True, exist_ok=True)
            prefix = f"capture_{capture_index}"
            img_dest = captures_dir / f"{prefix}.jpg"
            shutil.copy2(frame_path, img_dest)
            sc.image_path = f"captures/{prefix}.jpg"

            json_dest = captures_dir / f"{prefix}.json"
            json_dest.write_text(sc.model_dump_json(indent=2))

        return sc
