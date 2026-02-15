"""Standardized output directory structure and manifest I/O for PlanOpticon."""

import logging
from pathlib import Path
from typing import Dict

from video_processor.models import BatchManifest, VideoManifest

logger = logging.getLogger(__name__)


def create_video_output_dirs(output_dir: str | Path, video_name: str) -> Dict[str, Path]:
    """
    Create standardized single-video output directory structure.

    Layout:
        output_dir/
            manifest.json
            transcript/
                transcript.json, .txt, .srt
            frames/
                frame_0000.jpg ...
            diagrams/
                diagram_0.json, .jpg, .mermaid, .svg, .png
            captures/
                capture_0.jpg, capture_0.json
            results/
                analysis.md, .html, .pdf
                knowledge_graph.json
                key_points.json
                action_items.json
            cache/

    Returns dict mapping directory names to Path objects.
    """
    base = Path(output_dir)
    dirs = {
        "root": base,
        "transcript": base / "transcript",
        "frames": base / "frames",
        "diagrams": base / "diagrams",
        "captures": base / "captures",
        "results": base / "results",
        "cache": base / "cache",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    logger.info(f"Created output structure for '{video_name}' at {base}")
    return dirs


def create_batch_output_dirs(output_dir: str | Path, batch_name: str) -> Dict[str, Path]:
    """
    Create standardized batch output directory structure.

    Layout:
        output_dir/
            manifest.json
            batch_summary.md
            knowledge_graph.json
            videos/
                video_1/manifest.json
                video_2/manifest.json
                ...

    Returns dict mapping directory names to Path objects.
    """
    base = Path(output_dir)
    dirs = {
        "root": base,
        "videos": base / "videos",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    logger.info(f"Created batch output structure for '{batch_name}' at {base}")
    return dirs


# --- Manifest I/O ---


def write_video_manifest(manifest: VideoManifest, output_dir: str | Path) -> Path:
    """Write a VideoManifest to output_dir/manifest.json."""
    path = Path(output_dir) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2))
    logger.info(f"Wrote video manifest to {path}")
    return path


def read_video_manifest(output_dir: str | Path) -> VideoManifest:
    """Read a VideoManifest from output_dir/manifest.json."""
    path = Path(output_dir) / "manifest.json"
    return VideoManifest.model_validate_json(path.read_text())


def write_batch_manifest(manifest: BatchManifest, output_dir: str | Path) -> Path:
    """Write a BatchManifest to output_dir/manifest.json."""
    path = Path(output_dir) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2))
    logger.info(f"Wrote batch manifest to {path}")
    return path


def read_batch_manifest(output_dir: str | Path) -> BatchManifest:
    """Read a BatchManifest from output_dir/manifest.json."""
    path = Path(output_dir) / "manifest.json"
    return BatchManifest.model_validate_json(path.read_text())
