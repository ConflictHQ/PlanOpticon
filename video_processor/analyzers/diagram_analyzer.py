"""Diagram analysis using vision model classification and single-pass extraction."""

import hashlib
import json
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple, Union

from tqdm import tqdm

from video_processor.models import DiagramResult, DiagramType, ScreenCapture
from video_processor.providers.manager import ProviderManager

logger = logging.getLogger(__name__)

# Default max workers for parallel frame analysis
_DEFAULT_MAX_WORKERS = 4

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

# Rich screenshot extraction prompt — extracts knowledge from shared screens
_SCREENSHOT_EXTRACT_PROMPT = """\
Analyze this screenshot from a video recording. Extract all visible knowledge.
This is shared screen content (slides, code, documents, browser, terminal, etc.).

Return ONLY a JSON object (no markdown fences):
{
  "content_type": "slide"|"code"|"document"|"terminal"|"browser"|"chat"|"other",
  "caption": "one-sentence description of what is shown",
  "text_content": "all visible text, preserving structure and line breaks",
  "entities": ["named things visible: people, technologies, tools, services, \
projects, libraries, APIs, error codes, URLs, file paths"],
  "topics": ["concepts or subjects this content is about"]
}

For text_content: extract ALL readable text — code, titles, bullet points, URLs,
error messages, terminal output, chat messages, file names. Be thorough.
For entities: extract specific named things, not generic words.
For topics: extract 2-5 high-level topics this content relates to.
"""


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


def _frame_hash(path: Path) -> str:
    """Content-based hash for a frame file (first 8KB + size for speed)."""
    h = hashlib.sha256()
    h.update(str(path.stat().st_size).encode())
    with open(path, "rb") as f:
        h.update(f.read(8192))
    return h.hexdigest()[:16]


class _FrameCache:
    """Simple JSON file cache for frame classification/analysis results."""

    def __init__(self, cache_path: Optional[Path]):
        self._path = cache_path
        self._data: dict = {}
        if cache_path and cache_path.exists():
            try:
                self._data = json.loads(cache_path.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def get(self, key: str) -> Optional[dict]:
        return self._data.get(key)

    def set(self, key: str, value: dict) -> None:
        self._data[key] = value

    def save(self) -> None:
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, indent=2))


class DiagramAnalyzer:
    """Vision model-based diagram detection and analysis."""

    def __init__(
        self,
        provider_manager: Optional[ProviderManager] = None,
        confidence_threshold: float = 0.3,
        max_workers: int = _DEFAULT_MAX_WORKERS,
    ):
        self.pm = provider_manager or ProviderManager()
        self.confidence_threshold = confidence_threshold
        self.max_workers = max_workers

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

    def extract_screenshot_knowledge(self, image_path: Union[str, Path]) -> dict:
        """Extract knowledge from a screenshot — text, entities, topics."""
        image_bytes = _read_image_bytes(image_path)
        raw = self.pm.analyze_image(image_bytes, _SCREENSHOT_EXTRACT_PROMPT, max_tokens=2048)
        result = _parse_json_response(raw)
        return result or {}

    def process_frames(
        self,
        frame_paths: List[Union[str, Path]],
        diagrams_dir: Optional[Path] = None,
        captures_dir: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
    ) -> Tuple[List[DiagramResult], List[ScreenCapture]]:
        """
        Process a list of extracted frames: classify, analyze diagrams, screengrab fallback.

        Classification and analysis run in parallel using a thread pool. Results are
        cached by frame content hash so re-runs skip already-analyzed frames.

        Thresholds:
          - confidence >= 0.7  → full diagram analysis (story 3.2)
          - 0.3 <= confidence < 0.7 → screengrab fallback (story 3.3)
          - confidence < 0.3 → skip

        Returns (diagrams, screen_captures).
        """
        # Set up cache
        cache_path = None
        if cache_dir:
            cache_path = cache_dir / "frame_analysis_cache.json"
        elif diagrams_dir:
            cache_path = diagrams_dir.parent / "frame_analysis_cache.json"
        cache = _FrameCache(cache_path)

        frame_paths = [Path(fp) for fp in frame_paths]

        # --- Phase 1: Parallel classification ---
        classifications: dict[int, dict] = {}
        cache_hits = 0

        def _classify_one(idx: int, fp: Path) -> Tuple[int, dict, bool]:
            fhash = _frame_hash(fp)
            cached = cache.get(f"classify:{fhash}")
            if cached is not None:
                return idx, cached, True
            try:
                result = self.classify_frame(fp)
            except Exception as e:
                logger.warning(f"Classification failed for frame {idx}: {e}")
                result = {"is_diagram": False, "confidence": 0.0}
            cache.set(f"classify:{fhash}", result)
            return idx, result, False

        workers = min(self.max_workers, len(frame_paths)) if frame_paths else 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_classify_one, i, fp): i for i, fp in enumerate(frame_paths)}
            pbar = tqdm(
                as_completed(futures),
                total=len(futures),
                desc="Classifying frames",
                unit="frame",
            )
            for future in pbar:
                idx, result, from_cache = future.result()
                classifications[idx] = result
                if from_cache:
                    cache_hits += 1

        if cache_hits:
            logger.info(f"Classification: {cache_hits}/{len(frame_paths)} from cache")

        # --- Phase 2: Parallel analysis/extraction for qualifying frames ---
        high_conf = []  # (idx, fp, classification)
        med_conf = []

        for idx in sorted(classifications):
            conf = float(classifications[idx].get("confidence", 0.0))
            if conf >= 0.7:
                high_conf.append((idx, frame_paths[idx], classifications[idx]))
            elif conf >= self.confidence_threshold:
                med_conf.append((idx, frame_paths[idx], classifications[idx]))

        # Analyze high-confidence diagrams in parallel
        analysis_results: dict[int, dict] = {}

        def _analyze_one(idx: int, fp: Path) -> Tuple[int, dict, bool]:
            fhash = _frame_hash(fp)
            cached = cache.get(f"analyze:{fhash}")
            if cached is not None:
                return idx, cached, True
            try:
                result = self.analyze_diagram_single_pass(fp)
            except Exception as e:
                logger.warning(f"Diagram analysis failed for frame {idx}: {e}")
                result = {}
            cache.set(f"analyze:{fhash}", result)
            return idx, result, False

        if high_conf:
            workers = min(self.max_workers, len(high_conf))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_analyze_one, idx, fp): idx for idx, fp, _ in high_conf}
                pbar = tqdm(
                    as_completed(futures),
                    total=len(futures),
                    desc="Analyzing diagrams",
                    unit="diagram",
                )
                for future in pbar:
                    idx, result, _ = future.result()
                    analysis_results[idx] = result

        # Extract knowledge from medium-confidence frames in parallel
        extraction_results: dict[int, dict] = {}

        def _extract_one(idx: int, fp: Path) -> Tuple[int, dict, bool]:
            fhash = _frame_hash(fp)
            cached = cache.get(f"extract:{fhash}")
            if cached is not None:
                return idx, cached, True
            try:
                result = self.extract_screenshot_knowledge(fp)
            except Exception as e:
                logger.warning(f"Screenshot extraction failed for frame {idx}: {e}")
                result = {}
            cache.set(f"extract:{fhash}", result)
            return idx, result, False

        if med_conf:
            workers = min(self.max_workers, len(med_conf))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_extract_one, idx, fp): idx for idx, fp, _ in med_conf}
                pbar = tqdm(
                    as_completed(futures),
                    total=len(futures),
                    desc="Extracting screenshots",
                    unit="capture",
                )
                for future in pbar:
                    idx, result, _ = future.result()
                    extraction_results[idx] = result

        # --- Phase 3: Build results (sequential for stable ordering) ---
        diagrams: List[DiagramResult] = []
        captures: List[ScreenCapture] = []
        diagram_idx = 0
        capture_idx = 0

        for idx, fp, classification in high_conf:
            analysis = analysis_results.get(idx, {})
            confidence = float(classification.get("confidence", 0.0))

            if not analysis:
                # Analysis failed — fall back to screengrab with pre-fetched extraction
                extraction = extraction_results.get(idx)
                if extraction is None:
                    # Wasn't in med_conf, need to extract now
                    try:
                        extraction = self.extract_screenshot_knowledge(fp)
                    except Exception:
                        extraction = {}
                capture = self._build_screengrab(
                    fp, idx, capture_idx, captures_dir, confidence, extraction
                )
                captures.append(capture)
                capture_idx += 1
                continue

            dr = self._build_diagram_result(
                idx, fp, diagram_idx, diagrams_dir, confidence, classification, analysis
            )
            if dr:
                diagrams.append(dr)
                diagram_idx += 1
            else:
                capture = self._build_screengrab(fp, idx, capture_idx, captures_dir, confidence, {})
                captures.append(capture)
                capture_idx += 1

        for idx, fp, classification in med_conf:
            confidence = float(classification.get("confidence", 0.0))
            extraction = extraction_results.get(idx, {})
            logger.info(
                f"Frame {idx}: uncertain (confidence {confidence:.2f}), saving as screengrab"
            )
            capture = self._build_screengrab(
                fp, idx, capture_idx, captures_dir, confidence, extraction
            )
            captures.append(capture)
            capture_idx += 1

        # Save cache
        cache.save()

        logger.info(
            f"Diagram processing complete: {len(diagrams)} diagrams, {len(captures)} screengrabs"
        )
        return diagrams, captures

    def _build_diagram_result(
        self,
        frame_index: int,
        frame_path: Path,
        diagram_idx: int,
        diagrams_dir: Optional[Path],
        confidence: float,
        classification: dict,
        analysis: dict,
    ) -> Optional[DiagramResult]:
        """Build a DiagramResult from analysis data. Returns None on validation failure."""
        dtype = analysis.get("diagram_type", classification.get("diagram_type", "unknown"))
        try:
            diagram_type = DiagramType(dtype)
        except ValueError:
            diagram_type = DiagramType.unknown

        relationships = _normalize_relationships(analysis.get("relationships") or [])
        elements = _normalize_elements(analysis.get("elements") or [])
        text_content = _normalize_text_content(analysis.get("text_content"))

        try:
            dr = DiagramResult(
                frame_index=frame_index,
                diagram_type=diagram_type,
                confidence=confidence,
                description=analysis.get("description"),
                text_content=text_content,
                elements=elements,
                relationships=relationships,
                mermaid=analysis.get("mermaid"),
                chart_data=analysis.get("chart_data"),
            )
        except Exception as e:
            logger.warning(f"DiagramResult validation failed for frame {frame_index}: {e}")
            return None

        if diagrams_dir:
            diagrams_dir.mkdir(parents=True, exist_ok=True)
            prefix = f"diagram_{diagram_idx}"
            img_dest = diagrams_dir / f"{prefix}.jpg"
            shutil.copy2(frame_path, img_dest)
            dr.image_path = f"diagrams/{prefix}.jpg"
            if dr.mermaid:
                mermaid_dest = diagrams_dir / f"{prefix}.mermaid"
                mermaid_dest.write_text(dr.mermaid)
                dr.mermaid_path = f"diagrams/{prefix}.mermaid"
            json_dest = diagrams_dir / f"{prefix}.json"
            json_dest.write_text(dr.model_dump_json(indent=2))

        return dr

    def _build_screengrab(
        self,
        frame_path: Path,
        frame_index: int,
        capture_index: int,
        captures_dir: Optional[Path],
        confidence: float,
        extraction: dict,
    ) -> ScreenCapture:
        """Build a ScreenCapture from extraction data."""
        caption = extraction.get("caption", "")
        content_type = extraction.get("content_type")
        text_content = extraction.get("text_content")
        raw_entities = extraction.get("entities", [])
        entities = [str(e) for e in raw_entities] if isinstance(raw_entities, list) else []
        raw_topics = extraction.get("topics", [])
        topics = [str(t) for t in raw_topics] if isinstance(raw_topics, list) else []

        if extraction:
            logger.info(
                f"Frame {frame_index}: extracted "
                f"{len(entities)} entities, "
                f"{len(topics)} topics from {content_type}"
            )

        sc = ScreenCapture(
            frame_index=frame_index,
            caption=caption,
            confidence=confidence,
            content_type=content_type,
            text_content=text_content,
            entities=entities,
            topics=topics,
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

    def _save_screengrab(
        self,
        frame_path: Path,
        frame_index: int,
        capture_index: int,
        captures_dir: Optional[Path],
        confidence: float,
    ) -> ScreenCapture:
        """Legacy entry point — extracts then delegates to _build_screengrab."""
        try:
            extraction = self.extract_screenshot_knowledge(frame_path)
        except Exception as e:
            logger.warning(f"Screenshot extraction failed for frame {frame_index}: {e}")
            extraction = {}
        return self._build_screengrab(
            frame_path, frame_index, capture_index, captures_dir, confidence, extraction
        )


def _normalize_relationships(raw_rels: list) -> List[str]:
    """Normalize relationships: llava sometimes returns dicts instead of strings."""
    relationships = []
    for rel in raw_rels:
        if isinstance(rel, str):
            relationships.append(rel)
        elif isinstance(rel, dict):
            src = rel.get("source", rel.get("from", "?"))
            dst = rel.get("destination", rel.get("to", "?"))
            label = rel.get("label", rel.get("relationship", ""))
            relationships.append(f"{src} -> {dst}: {label}" if label else f"{src} -> {dst}")
        else:
            relationships.append(str(rel))
    return relationships


def _normalize_elements(raw_elements: list) -> List[str]:
    """Normalize elements: llava may return dicts or nested lists."""
    elements = []
    for elem in raw_elements:
        if isinstance(elem, str):
            elements.append(elem)
        elif isinstance(elem, dict):
            name = elem.get("name", elem.get("element", ""))
            etype = elem.get("type", elem.get("element_type", ""))
            if name and etype:
                elements.append(f"{etype}: {name}")
            elif name:
                elements.append(name)
            else:
                elements.append(json.dumps(elem))
        elif isinstance(elem, list):
            elements.extend(str(e) for e in elem)
        else:
            elements.append(str(elem))
    return elements


def _normalize_text_content(raw_text) -> Optional[str]:
    """Normalize text_content: llava may return dict instead of string."""
    if isinstance(raw_text, dict):
        parts = []
        for k, v in raw_text.items():
            if isinstance(v, list):
                parts.append(f"{k}: {', '.join(str(x) for x in v)}")
            else:
                parts.append(f"{k}: {v}")
        return "\n".join(parts)
    elif isinstance(raw_text, list):
        return "\n".join(str(x) for x in raw_text)
    return raw_text
