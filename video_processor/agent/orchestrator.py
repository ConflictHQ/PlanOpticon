"""Agent orchestrator — intelligent, adaptive video processing."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from video_processor.models import (
    ProcessingStats,
    VideoManifest,
    VideoMetadata,
)
from video_processor.providers.manager import ProviderManager

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Agentic orchestrator that adaptively processes videos.

    Instead of running a fixed pipeline, the agent:
    - Decides processing depth per-video based on content analysis
    - Retries failed extractions with alternative strategies
    - Chains deeper analysis into sections that matter
    - Surfaces insights proactively
    """

    def __init__(
        self,
        provider_manager: Optional[ProviderManager] = None,
        max_retries: int = 2,
    ):
        self.pm = provider_manager or ProviderManager()
        self.max_retries = max_retries
        self._plan: List[Dict[str, Any]] = []
        self._results: Dict[str, Any] = {}
        self._insights: List[str] = []

    def process(
        self,
        input_path: Path,
        output_dir: Path,
        initial_depth: str = "standard",
        title: Optional[str] = None,
    ) -> VideoManifest:
        """
        Agentic processing of a single video.

        The agent plans, executes, and adapts based on results.
        """
        start_time = time.time()
        input_path = Path(input_path)
        output_dir = Path(output_dir)

        logger.info(f"Agent processing: {input_path}")

        # Phase 1: Plan
        plan = self._create_plan(input_path, initial_depth)
        logger.info(f"Agent plan: {len(plan)} steps")

        # Phase 2: Execute with adaptation
        for step in plan:
            self._execute_step(step, input_path, output_dir)

        # Phase 3: Reflect and enrich
        self._reflect_and_enrich(output_dir)

        # Phase 4: Build manifest
        elapsed = time.time() - start_time
        manifest = self._build_manifest(input_path, output_dir, title, elapsed)

        logger.info(
            f"Agent complete in {elapsed:.1f}s — "
            f"{len(manifest.diagrams)} diagrams, "
            f"{len(manifest.key_points)} key points, "
            f"{len(manifest.action_items)} action items, "
            f"{len(self._insights)} insights"
        )

        return manifest

    def _create_plan(self, input_path: Path, depth: str) -> List[Dict[str, Any]]:
        """Create an adaptive processing plan."""
        plan = [
            {"step": "extract_frames", "priority": "required"},
            {"step": "extract_audio", "priority": "required"},
            {"step": "transcribe", "priority": "required"},
        ]

        if depth in ("standard", "comprehensive"):
            plan.append({"step": "detect_diagrams", "priority": "standard"})
            plan.append({"step": "build_knowledge_graph", "priority": "standard"})

        plan.append({"step": "extract_key_points", "priority": "required"})
        plan.append({"step": "extract_action_items", "priority": "required"})

        if depth == "comprehensive":
            plan.append({"step": "deep_analysis", "priority": "comprehensive"})
            plan.append({"step": "cross_reference", "priority": "comprehensive"})

        plan.append({"step": "generate_reports", "priority": "required"})

        self._plan = plan
        return plan

    def _execute_step(self, step: Dict[str, Any], input_path: Path, output_dir: Path) -> None:
        """Execute a single step with retry logic."""
        step_name = step["step"]
        logger.info(f"Agent step: {step_name}")

        for attempt in range(1, self.max_retries + 1):
            try:
                result = self._run_step(step_name, input_path, output_dir)
                self._results[step_name] = result

                # Adaptive: check if we should add more steps
                self._adapt_plan(step_name, result)
                return

            except Exception as e:
                logger.warning(
                    f"Step {step_name} failed (attempt {attempt}/{self.max_retries}): {e}"
                )
                if attempt == self.max_retries:
                    logger.error(f"Step {step_name} failed after {self.max_retries} attempts")
                    self._results[step_name] = {"error": str(e)}

                    # Try fallback strategy
                    fallback = self._get_fallback(step_name)
                    if fallback:
                        logger.info(f"Trying fallback for {step_name}: {fallback}")
                        try:
                            result = self._run_step(fallback, input_path, output_dir)
                            self._results[step_name] = result
                        except Exception as fe:
                            logger.error(f"Fallback {fallback} also failed: {fe}")

    def _run_step(self, step_name: str, input_path: Path, output_dir: Path) -> Any:
        """Run a specific processing step."""
        from video_processor.output_structure import create_video_output_dirs

        dirs = create_video_output_dirs(output_dir, input_path.stem)

        if step_name == "extract_frames":
            from video_processor.extractors.frame_extractor import extract_frames, save_frames

            frames = extract_frames(input_path)
            paths = save_frames(frames, dirs["frames"], "frame")
            return {"frames": frames, "paths": paths}

        elif step_name == "extract_audio":
            from video_processor.extractors.audio_extractor import AudioExtractor

            extractor = AudioExtractor()
            audio_path = extractor.extract_audio(
                input_path, output_path=dirs["root"] / "audio" / f"{input_path.stem}.wav"
            )
            props = extractor.get_audio_properties(audio_path)
            return {"audio_path": audio_path, "properties": props}

        elif step_name == "transcribe":
            audio_result = self._results.get("extract_audio", {})
            audio_path = audio_result.get("audio_path")
            if not audio_path:
                raise RuntimeError("No audio available for transcription")

            transcription = self.pm.transcribe_audio(audio_path)
            text = transcription.get("text", "")

            # Save transcript
            dirs["transcript"].mkdir(parents=True, exist_ok=True)
            (dirs["transcript"] / "transcript.json").write_text(json.dumps(transcription, indent=2))
            (dirs["transcript"] / "transcript.txt").write_text(text)
            return transcription

        elif step_name == "detect_diagrams":
            from video_processor.analyzers.diagram_analyzer import DiagramAnalyzer

            frame_result = self._results.get("extract_frames", {})
            paths = frame_result.get("paths", [])
            if not paths:
                return {"diagrams": [], "captures": []}

            analyzer = DiagramAnalyzer(provider_manager=self.pm)
            diagrams, captures = analyzer.process_frames(
                paths[:15], diagrams_dir=dirs["diagrams"], captures_dir=dirs["captures"]
            )
            return {"diagrams": diagrams, "captures": captures}

        elif step_name == "build_knowledge_graph":
            from video_processor.integrators.knowledge_graph import KnowledgeGraph

            transcript = self._results.get("transcribe", {})
            kg = KnowledgeGraph(provider_manager=self.pm)
            kg.process_transcript(transcript)

            diagram_result = self._results.get("detect_diagrams", {})
            diagrams = diagram_result.get("diagrams", [])
            if diagrams:
                kg.process_diagrams([d.model_dump() for d in diagrams])

            kg.save(dirs["results"] / "knowledge_graph.json")
            return {"knowledge_graph": kg}

        elif step_name == "extract_key_points":
            transcript = self._results.get("transcribe", {})
            text = transcript.get("text", "")
            if not text:
                return {"key_points": []}

            from video_processor.pipeline import _extract_key_points

            kps = _extract_key_points(self.pm, text)
            return {"key_points": kps}

        elif step_name == "extract_action_items":
            transcript = self._results.get("transcribe", {})
            text = transcript.get("text", "")
            if not text:
                return {"action_items": []}

            from video_processor.pipeline import _extract_action_items

            items = _extract_action_items(self.pm, text)
            return {"action_items": items}

        elif step_name == "deep_analysis":
            return self._deep_analysis(output_dir)

        elif step_name == "cross_reference":
            return self._cross_reference()

        elif step_name == "generate_reports":
            return self._generate_reports(input_path, output_dir)

        elif step_name == "screengrab_fallback":
            # Already handled in detect_diagrams
            return {}

        else:
            raise ValueError(f"Unknown step: {step_name}")

    def _adapt_plan(self, completed_step: str, result: Any) -> None:
        """Adapt the plan based on step results."""

        if completed_step == "transcribe":
            text = result.get("text", "") if isinstance(result, dict) else ""
            # If transcript is very long, add deep analysis
            if len(text) > 10000 and not any(s["step"] == "deep_analysis" for s in self._plan):
                self._plan.append({"step": "deep_analysis", "priority": "adaptive"})
                logger.info("Agent adapted: adding deep analysis for long transcript")

        elif completed_step == "detect_diagrams":
            diagrams = result.get("diagrams", []) if isinstance(result, dict) else []
            captures = result.get("captures", []) if isinstance(result, dict) else []
            # If many diagrams found, ensure cross-referencing
            if len(diagrams) >= 3 and not any(s["step"] == "cross_reference" for s in self._plan):
                self._plan.append({"step": "cross_reference", "priority": "adaptive"})
                logger.info("Agent adapted: adding cross-reference for diagram-heavy video")

            if len(captures) > len(diagrams):
                self._insights.append(
                    f"Many uncertain frames ({len(captures)} captures vs {len(diagrams)} diagrams) "
                    "— consider re-processing with comprehensive depth"
                )

    def _get_fallback(self, step_name: str) -> Optional[str]:
        """Get a fallback strategy for a failed step."""
        fallbacks = {
            "detect_diagrams": "screengrab_fallback",
        }
        return fallbacks.get(step_name)

    def _deep_analysis(self, output_dir: Path) -> Dict:
        """Perform deeper analysis on the transcript."""
        transcript = self._results.get("transcribe", {})
        text = transcript.get("text", "")
        if not text or not self.pm:
            return {}

        prompt = (
            "Analyze this transcript in depth. Identify:\n"
            "1. Hidden assumptions or risks\n"
            "2. Decisions that were made (explicitly or implicitly)\n"
            "3. Topics that need follow-up\n"
            "4. Potential disagreements or tensions\n\n"
            f"TRANSCRIPT:\n{text[:10000]}\n\n"
            "Return a JSON object:\n"
            '{"decisions": [...], "risks": [...], "follow_ups": [...], "tensions": [...]}\n'
            "Return ONLY the JSON."
        )

        try:
            from video_processor.utils.json_parsing import parse_json_from_response

            raw = self.pm.chat([{"role": "user", "content": prompt}], temperature=0.4)
            parsed = parse_json_from_response(raw)
            if isinstance(parsed, dict):
                for category, items in parsed.items():
                    if isinstance(items, list):
                        for item in items:
                            self._insights.append(f"[{category}] {item}")
                return parsed
        except Exception as e:
            logger.warning(f"Deep analysis failed: {e}")

        return {}

    def _cross_reference(self) -> Dict:
        """Cross-reference entities between transcript and diagrams."""
        from video_processor.analyzers.content_analyzer import ContentAnalyzer

        kg_result = self._results.get("build_knowledge_graph", {})
        kg = kg_result.get("knowledge_graph")
        if not kg:
            return {}

        kp_result = self._results.get("extract_key_points", {})
        key_points = kp_result.get("key_points", [])

        diagram_result = self._results.get("detect_diagrams", {})
        diagrams = diagram_result.get("diagrams", [])

        analyzer = ContentAnalyzer(provider_manager=self.pm)
        transcript = self._results.get("transcribe", {})

        if key_points and diagrams:
            diagram_dicts = [d.model_dump() for d in diagrams]
            enriched = analyzer.enrich_key_points(
                key_points, diagram_dicts, transcript.get("text", "")
            )
            self._results["extract_key_points"]["key_points"] = enriched

        return {"enriched": True}

    def _generate_reports(self, input_path: Path, output_dir: Path) -> Dict:
        """Generate all output reports."""
        from video_processor.integrators.plan_generator import PlanGenerator
        from video_processor.output_structure import create_video_output_dirs

        dirs = create_video_output_dirs(output_dir, input_path.stem)

        transcript = self._results.get("transcribe", {})
        kp_result = self._results.get("extract_key_points", {})
        key_points = kp_result.get("key_points", [])
        ai_result = self._results.get("extract_action_items", {})
        ai_result.get("action_items", [])
        diagram_result = self._results.get("detect_diagrams", {})
        diagrams = diagram_result.get("diagrams", [])
        kg_result = self._results.get("build_knowledge_graph", {})
        kg = kg_result.get("knowledge_graph")

        gen = PlanGenerator(provider_manager=self.pm, knowledge_graph=kg)
        md_path = dirs["results"] / "analysis.md"
        gen.generate_markdown(
            transcript=transcript,
            key_points=[kp.model_dump() for kp in key_points],
            diagrams=[d.model_dump() for d in diagrams],
            knowledge_graph=kg.to_dict() if kg else {},
            video_title=input_path.stem,
            output_path=md_path,
        )

        # Add agent insights to report
        if self._insights:
            insights_md = "\n## Agent Insights\n\n"
            for insight in self._insights:
                insights_md += f"- {insight}\n"
            with open(md_path, "a") as f:
                f.write(insights_md)

        return {"report_path": str(md_path)}

    def _build_manifest(
        self,
        input_path: Path,
        output_dir: Path,
        title: Optional[str],
        elapsed: float,
    ) -> VideoManifest:
        """Build the final manifest."""
        frame_result = self._results.get("extract_frames", {})
        audio_result = self._results.get("extract_audio", {})
        diagram_result = self._results.get("detect_diagrams", {})
        kp_result = self._results.get("extract_key_points", {})
        ai_result = self._results.get("extract_action_items", {})

        diagrams = diagram_result.get("diagrams", []) if isinstance(diagram_result, dict) else []
        captures = diagram_result.get("captures", []) if isinstance(diagram_result, dict) else []
        key_points = kp_result.get("key_points", []) if isinstance(kp_result, dict) else []
        action_items = ai_result.get("action_items", []) if isinstance(ai_result, dict) else []
        frames = frame_result.get("frames", []) if isinstance(frame_result, dict) else []
        paths = frame_result.get("paths", []) if isinstance(frame_result, dict) else []
        audio_props = audio_result.get("properties", {}) if isinstance(audio_result, dict) else {}

        return VideoManifest(
            video=VideoMetadata(
                title=title or f"Analysis of {input_path.stem}",
                source_path=str(input_path),
                duration_seconds=audio_props.get("duration"),
            ),
            stats=ProcessingStats(
                duration_seconds=elapsed,
                frames_extracted=len(frames),
                diagrams_detected=len(diagrams),
                screen_captures=len(captures),
                transcript_duration_seconds=audio_props.get("duration"),
                models_used=self.pm.get_models_used(),
            ),
            key_points=key_points,
            action_items=action_items,
            diagrams=diagrams,
            screen_captures=captures,
            frame_paths=[f"frames/{Path(p).name}" for p in paths],
        )

    @property
    def insights(self) -> List[str]:
        """Return agent insights generated during processing."""
        return list(self._insights)
