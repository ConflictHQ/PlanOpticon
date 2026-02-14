"""Core video processing pipeline — the reusable function both CLI commands call."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from video_processor.analyzers.diagram_analyzer import DiagramAnalyzer
from video_processor.extractors.audio_extractor import AudioExtractor
from video_processor.extractors.frame_extractor import extract_frames, save_frames
from video_processor.integrators.knowledge_graph import KnowledgeGraph
from video_processor.integrators.plan_generator import PlanGenerator
from video_processor.models import (
    ActionItem,
    KeyPoint,
    ProcessingStats,
    VideoManifest,
    VideoMetadata,
)
from video_processor.output_structure import create_video_output_dirs, write_video_manifest
from video_processor.providers.manager import ProviderManager
from video_processor.utils.export import export_all_formats

logger = logging.getLogger(__name__)


def process_single_video(
    input_path: str | Path,
    output_dir: str | Path,
    provider_manager: Optional[ProviderManager] = None,
    depth: str = "standard",
    focus_areas: Optional[list[str]] = None,
    sampling_rate: float = 0.5,
    change_threshold: float = 0.15,
    use_gpu: bool = False,
    title: Optional[str] = None,
) -> VideoManifest:
    """
    Full pipeline: frames -> audio -> transcription -> diagrams -> KG -> report -> export.

    Returns a populated VideoManifest.
    """
    start_time = time.time()
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    pm = provider_manager or ProviderManager()
    focus_areas = focus_areas or []

    video_name = input_path.stem
    if not title:
        title = f"Analysis of {video_name}"

    # Create standardized directory structure
    dirs = create_video_output_dirs(output_dir, video_name)

    logger.info(f"Processing: {input_path}")
    logger.info(f"Depth: {depth}, Focus: {focus_areas or 'all'}")

    # --- Step 1: Extract frames ---
    logger.info("Extracting video frames...")
    frames = extract_frames(
        input_path,
        sampling_rate=sampling_rate,
        change_threshold=change_threshold,
        disable_gpu=not use_gpu,
    )
    frame_paths = save_frames(frames, dirs["frames"], "frame")
    logger.info(f"Extracted {len(frames)} frames")

    # --- Step 2: Extract audio ---
    logger.info("Extracting audio...")
    audio_extractor = AudioExtractor()
    audio_path = audio_extractor.extract_audio(
        input_path, output_path=dirs["root"] / "audio" / f"{video_name}.wav"
    )
    audio_props = audio_extractor.get_audio_properties(audio_path)

    # --- Step 3: Transcribe ---
    logger.info("Transcribing audio...")
    transcription = pm.transcribe_audio(audio_path)
    transcript_text = transcription.get("text", "")
    segments = transcription.get("segments", [])

    # Save transcript files
    transcript_data = {
        "text": transcript_text,
        "segments": segments,
        "duration": transcription.get("duration") or audio_props.get("duration"),
        "language": transcription.get("language"),
        "provider": transcription.get("provider"),
        "model": transcription.get("model"),
    }
    transcript_json = dirs["transcript"] / "transcript.json"
    transcript_json.write_text(json.dumps(transcript_data, indent=2))

    transcript_txt = dirs["transcript"] / "transcript.txt"
    transcript_txt.write_text(transcript_text)

    # SRT
    transcript_srt = dirs["transcript"] / "transcript.srt"
    srt_lines = []
    for i, seg in enumerate(segments):
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        srt_lines.append(str(i + 1))
        srt_lines.append(
            f"{_format_srt_time(start)} --> {_format_srt_time(end)}"
        )
        srt_lines.append(seg.get("text", "").strip())
        srt_lines.append("")
    transcript_srt.write_text("\n".join(srt_lines))

    # --- Step 4: Diagram extraction ---
    diagrams = []
    screen_captures = []
    if depth != "basic" and (not focus_areas or "diagrams" in focus_areas):
        logger.info("Analyzing visual elements...")
        analyzer = DiagramAnalyzer(provider_manager=pm)
        max_frames = 10 if depth == "standard" else 20
        subset = frame_paths[:min(max_frames, len(frame_paths))]
        diagrams, screen_captures = analyzer.process_frames(
            subset, diagrams_dir=dirs["diagrams"], captures_dir=dirs["captures"]
        )

    # --- Step 5: Knowledge graph ---
    logger.info("Building knowledge graph...")
    kg = KnowledgeGraph(provider_manager=pm)
    kg.process_transcript(transcript_data)
    if diagrams:
        diagram_dicts = [d.model_dump() for d in diagrams]
        kg.process_diagrams(diagram_dicts)
    kg_path = kg.save(dirs["results"] / "knowledge_graph.json")

    # --- Step 6: Extract key points & action items ---
    key_points = _extract_key_points(pm, transcript_text)
    action_items = _extract_action_items(pm, transcript_text)

    # Save structured data
    kp_path = dirs["results"] / "key_points.json"
    kp_path.write_text(json.dumps([kp.model_dump() for kp in key_points], indent=2))

    ai_path = dirs["results"] / "action_items.json"
    ai_path.write_text(json.dumps([ai.model_dump() for ai in action_items], indent=2))

    # --- Step 7: Generate markdown report ---
    logger.info("Generating report...")
    plan_gen = PlanGenerator(provider_manager=pm, knowledge_graph=kg)
    md_path = dirs["results"] / "analysis.md"
    plan_gen.generate_markdown(
        transcript=transcript_data,
        key_points=[kp.model_dump() for kp in key_points],
        diagrams=[d.model_dump() for d in diagrams],
        knowledge_graph=kg.to_dict(),
        video_title=title,
        output_path=md_path,
    )

    # --- Build manifest ---
    elapsed = time.time() - start_time
    manifest = VideoManifest(
        video=VideoMetadata(
            title=title,
            source_path=str(input_path),
            duration_seconds=audio_props.get("duration"),
        ),
        stats=ProcessingStats(
            start_time=datetime.now().isoformat(),
            duration_seconds=elapsed,
            frames_extracted=len(frames),
            diagrams_detected=len(diagrams),
            screen_captures=len(screen_captures),
            transcript_duration_seconds=audio_props.get("duration"),
            models_used=pm.get_models_used(),
        ),
        transcript_json="transcript/transcript.json",
        transcript_txt="transcript/transcript.txt",
        transcript_srt="transcript/transcript.srt",
        analysis_md="results/analysis.md",
        knowledge_graph_json="results/knowledge_graph.json",
        key_points_json="results/key_points.json",
        action_items_json="results/action_items.json",
        key_points=key_points,
        action_items=action_items,
        diagrams=diagrams,
        screen_captures=screen_captures,
        frame_paths=[f"frames/{Path(p).name}" for p in frame_paths],
    )

    # --- Step 8: Export all formats ---
    logger.info("Exporting multi-format outputs...")
    manifest = export_all_formats(output_dir, manifest)

    # Write manifest
    write_video_manifest(manifest, output_dir)

    logger.info(f"Processing complete in {elapsed:.1f}s: {len(diagrams)} diagrams, "
                f"{len(screen_captures)} captures, {len(key_points)} key points, "
                f"{len(action_items)} action items")

    return manifest


def _extract_key_points(pm: ProviderManager, text: str) -> list[KeyPoint]:
    """Extract key points via LLM."""
    from video_processor.utils.json_parsing import parse_json_from_response

    prompt = (
        "Extract the key points from this transcript.\n\n"
        f"TRANSCRIPT:\n{text[:8000]}\n\n"
        'Return a JSON array: [{"point": "...", "topic": "...", "details": "..."}]\n'
        "Return ONLY the JSON array."
    )
    try:
        raw = pm.chat([{"role": "user", "content": prompt}], temperature=0.3)
        parsed = parse_json_from_response(raw)
        if isinstance(parsed, list):
            return [
                KeyPoint(
                    point=item.get("point", ""),
                    topic=item.get("topic"),
                    details=item.get("details"),
                )
                for item in parsed
                if isinstance(item, dict) and item.get("point")
            ]
    except Exception as e:
        logger.warning(f"Key point extraction failed: {e}")
    return []


def _extract_action_items(pm: ProviderManager, text: str) -> list[ActionItem]:
    """Extract action items via LLM."""
    from video_processor.utils.json_parsing import parse_json_from_response

    prompt = (
        "Extract all action items from this transcript.\n\n"
        f"TRANSCRIPT:\n{text[:8000]}\n\n"
        'Return a JSON array: [{"action": "...", "assignee": "...", "deadline": "...", '
        '"priority": "...", "context": "..."}]\n'
        "Return ONLY the JSON array."
    )
    try:
        raw = pm.chat([{"role": "user", "content": prompt}], temperature=0.3)
        parsed = parse_json_from_response(raw)
        if isinstance(parsed, list):
            return [
                ActionItem(
                    action=item.get("action", ""),
                    assignee=item.get("assignee"),
                    deadline=item.get("deadline"),
                    priority=item.get("priority"),
                    context=item.get("context"),
                )
                for item in parsed
                if isinstance(item, dict) and item.get("action")
            ]
    except Exception as e:
        logger.warning(f"Action item extraction failed: {e}")
    return []


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
