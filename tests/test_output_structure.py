"""Tests for output structure and manifest I/O."""

import json
import tempfile
from pathlib import Path

import pytest

from video_processor.models import (
    ActionItem,
    BatchManifest,
    BatchVideoEntry,
    DiagramResult,
    KeyPoint,
    ProcessingStats,
    VideoManifest,
    VideoMetadata,
)
from video_processor.output_structure import (
    create_batch_output_dirs,
    create_video_output_dirs,
    read_batch_manifest,
    read_video_manifest,
    write_batch_manifest,
    write_video_manifest,
)


class TestCreateVideoOutputDirs:
    def test_creates_all_directories(self, tmp_path):
        dirs = create_video_output_dirs(tmp_path / "output", "test_video")
        assert dirs["root"].exists()
        assert dirs["transcript"].exists()
        assert dirs["frames"].exists()
        assert dirs["diagrams"].exists()
        assert dirs["captures"].exists()
        assert dirs["results"].exists()
        assert dirs["cache"].exists()

    def test_expected_layout(self, tmp_path):
        dirs = create_video_output_dirs(tmp_path / "output", "my_video")
        base = tmp_path / "output"
        assert dirs["transcript"] == base / "transcript"
        assert dirs["frames"] == base / "frames"
        assert dirs["diagrams"] == base / "diagrams"
        assert dirs["captures"] == base / "captures"
        assert dirs["results"] == base / "results"
        assert dirs["cache"] == base / "cache"

    def test_idempotent(self, tmp_path):
        out = tmp_path / "output"
        dirs1 = create_video_output_dirs(out, "v")
        dirs2 = create_video_output_dirs(out, "v")
        assert dirs1 == dirs2


class TestCreateBatchOutputDirs:
    def test_creates_directories(self, tmp_path):
        dirs = create_batch_output_dirs(tmp_path / "batch", "my_batch")
        assert dirs["root"].exists()
        assert dirs["videos"].exists()

    def test_expected_layout(self, tmp_path):
        dirs = create_batch_output_dirs(tmp_path / "batch", "b")
        base = tmp_path / "batch"
        assert dirs["videos"] == base / "videos"


class TestVideoManifestIO:
    def _sample_manifest(self) -> VideoManifest:
        return VideoManifest(
            video=VideoMetadata(title="Test", duration_seconds=120.0),
            stats=ProcessingStats(frames_extracted=10, diagrams_detected=2),
            transcript_json="transcript/transcript.json",
            analysis_md="results/analysis.md",
            key_points=[KeyPoint(point="Point 1")],
            action_items=[ActionItem(action="Do thing")],
            diagrams=[DiagramResult(frame_index=0, confidence=0.9)],
        )

    def test_write_and_read(self, tmp_path):
        manifest = self._sample_manifest()
        write_video_manifest(manifest, tmp_path)

        restored = read_video_manifest(tmp_path)
        assert restored.video.title == "Test"
        assert restored.stats.frames_extracted == 10
        assert len(restored.key_points) == 1
        assert len(restored.diagrams) == 1

    def test_manifest_file_is_valid_json(self, tmp_path):
        manifest = self._sample_manifest()
        write_video_manifest(manifest, tmp_path)

        path = tmp_path / "manifest.json"
        data = json.loads(path.read_text())
        assert data["version"] == "1.0"
        assert data["video"]["title"] == "Test"

    def test_creates_parent_dirs(self, tmp_path):
        manifest = self._sample_manifest()
        nested = tmp_path / "a" / "b" / "c"
        write_video_manifest(manifest, nested)
        assert (nested / "manifest.json").exists()


class TestBatchManifestIO:
    def _sample_batch(self) -> BatchManifest:
        return BatchManifest(
            title="Test Batch",
            total_videos=2,
            completed_videos=2,
            videos=[
                BatchVideoEntry(
                    video_name="v1",
                    manifest_path="videos/v1/manifest.json",
                    status="completed",
                ),
                BatchVideoEntry(
                    video_name="v2",
                    manifest_path="videos/v2/manifest.json",
                    status="completed",
                ),
            ],
            batch_summary_md="batch_summary.md",
        )

    def test_write_and_read(self, tmp_path):
        manifest = self._sample_batch()
        write_batch_manifest(manifest, tmp_path)

        restored = read_batch_manifest(tmp_path)
        assert restored.title == "Test Batch"
        assert restored.total_videos == 2
        assert len(restored.videos) == 2
        assert restored.videos[0].video_name == "v1"

    def test_manifest_file_is_valid_json(self, tmp_path):
        manifest = self._sample_batch()
        write_batch_manifest(manifest, tmp_path)

        path = tmp_path / "manifest.json"
        data = json.loads(path.read_text())
        assert data["title"] == "Test Batch"
