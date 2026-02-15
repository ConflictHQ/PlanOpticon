"""Core video processing pipeline — the reusable function both CLI commands call."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from tqdm import tqdm

from video_processor.analyzers.diagram_analyzer import DiagramAnalyzer
from video_processor.extractors.audio_extractor import AudioExtractor
from video_processor.extractors.frame_extractor import (
    extract_frames,
    filter_people_frames,
    save_frames,
)
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
    periodic_capture_seconds: float = 30.0,
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

    steps = [
        "Extract frames",
        "Extract audio",
        "Transcribe",
        "Analyze visuals",
        "Build knowledge graph",
        "Extract key points",
        "Generate report",
        "Export formats",
    ]
    pipeline_bar = tqdm(steps, desc="Pipeline", unit="step", position=0)

    # --- Step 1: Extract frames ---
    pm.usage.start_step("Frame extraction")
    pipeline_bar.set_description("Pipeline: extracting frames")
    existing_frames = sorted(dirs["frames"].glob("frame_*.jpg"))
    people_removed = 0
    if existing_frames:
        frame_paths = existing_frames
        logger.info(f"Resuming: found {len(frame_paths)} frames on disk, skipping extraction")
    else:
        logger.info("Extracting video frames...")
        frames = extract_frames(
            input_path,
            sampling_rate=sampling_rate,
            change_threshold=change_threshold,
            periodic_capture_seconds=periodic_capture_seconds,
            disable_gpu=not use_gpu,
        )
        logger.info(f"Extracted {len(frames)} raw frames")

        # Filter out people/webcam frames before saving
        frames, people_removed = filter_people_frames(frames)
        frame_paths = save_frames(frames, dirs["frames"], "frame")
        logger.info(f"Saved {len(frames)} content frames ({people_removed} people frames filtered)")
    pipeline_bar.update(1)

    # --- Step 2: Extract audio ---
    pm.usage.start_step("Audio extraction")
    pipeline_bar.set_description("Pipeline: extracting audio")
    audio_path = dirs["root"] / "audio" / f"{video_name}.wav"
    audio_extractor = AudioExtractor()
    if audio_path.exists():
        logger.info(f"Resuming: found audio at {audio_path}, skipping extraction")
    else:
        logger.info("Extracting audio...")
        audio_path = audio_extractor.extract_audio(input_path, output_path=audio_path)
    audio_props = audio_extractor.get_audio_properties(audio_path)
    pipeline_bar.update(1)

    # --- Step 3: Transcribe ---
    pm.usage.start_step("Transcription")
    pipeline_bar.set_description("Pipeline: transcribing audio")
    transcript_json = dirs["transcript"] / "transcript.json"
    if transcript_json.exists():
        logger.info("Resuming: found transcript on disk, skipping transcription")
        transcript_data = json.loads(transcript_json.read_text())
        transcript_text = transcript_data.get("text", "")
        segments = transcript_data.get("segments", [])
    else:
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
            srt_lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
            srt_lines.append(seg.get("text", "").strip())
            srt_lines.append("")
        transcript_srt.write_text("\n".join(srt_lines))
    pipeline_bar.update(1)

    # --- Step 4: Diagram extraction ---
    pm.usage.start_step("Visual analysis")
    pipeline_bar.set_description("Pipeline: analyzing visuals")
    diagrams = []
    screen_captures = []
    existing_diagrams = (
        sorted(dirs["diagrams"].glob("diagram_*.json")) if dirs["diagrams"].exists() else []
    )
    if existing_diagrams:
        logger.info(f"Resuming: found {len(existing_diagrams)} diagrams on disk, skipping analysis")
        from video_processor.models import DiagramResult

        for dj in existing_diagrams:
            try:
                diagrams.append(DiagramResult.model_validate_json(dj.read_text()))
            except Exception as e:
                logger.warning(f"Failed to load diagram {dj}: {e}")
    elif depth != "basic" and (not focus_areas or "diagrams" in focus_areas):
        logger.info("Analyzing visual elements...")
        analyzer = DiagramAnalyzer(provider_manager=pm)
        max_frames = 10 if depth == "standard" else 20
        # Evenly sample across all frames rather than just taking the first N
        if len(frame_paths) <= max_frames:
            subset = frame_paths
        else:
            step = len(frame_paths) / max_frames
            subset = [frame_paths[int(i * step)] for i in range(max_frames)]
        diagrams, screen_captures = analyzer.process_frames(
            subset, diagrams_dir=dirs["diagrams"], captures_dir=dirs["captures"]
        )
    pipeline_bar.update(1)

    # --- Step 5: Knowledge graph ---
    pm.usage.start_step("Knowledge graph")
    pipeline_bar.set_description("Pipeline: building knowledge graph")
    kg_json_path = dirs["results"] / "knowledge_graph.json"
    if kg_json_path.exists():
        logger.info("Resuming: found knowledge graph on disk, loading")
        kg_data = json.loads(kg_json_path.read_text())
        kg = KnowledgeGraph(provider_manager=pm)
        kg = KnowledgeGraph.from_dict(kg_data)
    else:
        logger.info("Building knowledge graph...")
        kg = KnowledgeGraph(provider_manager=pm)
        kg.process_transcript(transcript_data)
        if diagrams:
            diagram_dicts = [d.model_dump() for d in diagrams]
            kg.process_diagrams(diagram_dicts)
        kg.save(kg_json_path)
    pipeline_bar.update(1)

    # --- Step 6: Extract key points & action items ---
    pm.usage.start_step("Key points & actions")
    pipeline_bar.set_description("Pipeline: extracting key points")
    kp_path = dirs["results"] / "key_points.json"
    ai_path = dirs["results"] / "action_items.json"
    if kp_path.exists() and ai_path.exists():
        logger.info("Resuming: found key points and action items on disk")
        key_points = [KeyPoint(**item) for item in json.loads(kp_path.read_text())]
        action_items = [ActionItem(**item) for item in json.loads(ai_path.read_text())]
    else:
        key_points = _extract_key_points(pm, transcript_text)
        action_items = _extract_action_items(pm, transcript_text)

        kp_path.write_text(json.dumps([kp.model_dump() for kp in key_points], indent=2))
        ai_path.write_text(json.dumps([ai.model_dump() for ai in action_items], indent=2))
    pipeline_bar.update(1)

    # --- Step 7: Generate markdown report ---
    pm.usage.start_step("Report generation")
    pipeline_bar.set_description("Pipeline: generating report")
    md_path = dirs["results"] / "analysis.md"
    if md_path.exists():
        logger.info("Resuming: found analysis report on disk, skipping generation")
    else:
        logger.info("Generating report...")
        plan_gen = PlanGenerator(provider_manager=pm, knowledge_graph=kg)
        plan_gen.generate_markdown(
            transcript=transcript_data,
            key_points=[kp.model_dump() for kp in key_points],
            diagrams=[d.model_dump() for d in diagrams],
            knowledge_graph=kg.to_dict(),
            video_title=title,
            output_path=md_path,
        )
    pipeline_bar.update(1)

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
            frames_extracted=len(frame_paths),
            people_frames_filtered=people_removed,
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
    pm.usage.start_step("Export formats")
    pipeline_bar.set_description("Pipeline: exporting formats")
    manifest = export_all_formats(output_dir, manifest)

    pm.usage.end_step()
    pipeline_bar.update(1)
    pipeline_bar.set_description("Pipeline: complete")
    pipeline_bar.close()

    # Write manifest
    write_video_manifest(manifest, output_dir)

    logger.info(
        f"Processing complete in {elapsed:.1f}s: {len(diagrams)} diagrams, "
        f"{len(screen_captures)} captures, {len(key_points)} key points, "
        f"{len(action_items)} action items"
    )

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
