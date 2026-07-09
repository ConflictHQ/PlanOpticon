"""Tests for the core video processing pipeline."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_processor.pipeline import (
    _extract_action_items,
    _extract_key_points,
    _format_srt_time,
    process_single_video,
)


class TestFormatSrtTime:
    def test_zero(self):
        assert _format_srt_time(0) == "00:00:00,000"

    def test_seconds(self):
        assert _format_srt_time(5.5) == "00:00:05,500"

    def test_minutes(self):
        assert _format_srt_time(90.0) == "00:01:30,000"

    def test_hours(self):
        assert _format_srt_time(3661.123) == "01:01:01,123"

    def test_large_value(self):
        result = _format_srt_time(7200.0)
        assert result == "02:00:00,000"


class TestExtractKeyPoints:
    def test_parses_valid_response(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps(
            [
                {"point": "Main point", "topic": "Architecture", "details": "Some details"},
                {"point": "Second point", "topic": None, "details": None},
            ]
        )
        result = _extract_key_points(pm, "Some transcript text here")
        assert len(result) == 2
        assert result[0].point == "Main point"
        assert result[0].topic == "Architecture"
        assert result[1].point == "Second point"

    def test_skips_invalid_items(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps(
            [
                {"point": "Valid", "topic": None},
                {"topic": "No point field"},
                {"point": "", "topic": "Empty point"},
            ]
        )
        result = _extract_key_points(pm, "text")
        assert len(result) == 1
        assert result[0].point == "Valid"

    def test_handles_error(self):
        pm = MagicMock()
        pm.chat.side_effect = Exception("API error")
        result = _extract_key_points(pm, "text")
        assert result == []

    def test_handles_non_list_response(self):
        pm = MagicMock()
        pm.chat.return_value = '{"not": "a list"}'
        result = _extract_key_points(pm, "text")
        assert result == []


class TestExtractActionItems:
    def test_parses_valid_response(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps(
            [
                {
                    "action": "Deploy fix",
                    "assignee": "Bob",
                    "deadline": "Friday",
                    "priority": "high",
                    "context": "Production",
                },
            ]
        )
        result = _extract_action_items(pm, "Some transcript text")
        assert len(result) == 1
        assert result[0].action == "Deploy fix"
        assert result[0].assignee == "Bob"

    def test_skips_invalid_items(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps(
            [
                {"action": "Valid action"},
                {"assignee": "No action field"},
                {"action": ""},
            ]
        )
        result = _extract_action_items(pm, "text")
        assert len(result) == 1

    def test_handles_error(self):
        pm = MagicMock()
        pm.chat.side_effect = Exception("API down")
        result = _extract_action_items(pm, "text")
        assert result == []


# ---------------------------------------------------------------------------
# process_single_video tests (heavily mocked)
# ---------------------------------------------------------------------------


def _make_mock_pm():
    """Build a mock ProviderManager with usage tracker and predictable responses."""
    from video_processor.utils.usage_tracker import UsageTracker

    pm = MagicMock()

    # Real usage tracker — the pipeline serializes it to usage.json
    pm.usage = UsageTracker()

    # transcribe_audio returns a simple transcript
    pm.transcribe_audio.return_value = {
        "text": "Alice discussed the Python deployment strategy with Bob.",
        "segments": [
            {"start": 0.0, "end": 5.0, "text": "Alice discussed the Python deployment strategy."},
            {"start": 5.0, "end": 10.0, "text": "Bob agreed on the timeline."},
        ],
        "duration": 10.0,
        "language": "en",
        "provider": "mock",
        "model": "mock-whisper",
    }

    # chat returns predictable JSON depending on the call
    def _chat_side_effect(messages, **kwargs):
        content = messages[0]["content"] if messages else ""
        if "key points" in content.lower():
            return json.dumps(
                [{"point": "Deployment strategy discussed", "topic": "DevOps", "details": "Python"}]
            )
        if "action items" in content.lower():
            return json.dumps(
                [{"action": "Deploy to production", "assignee": "Bob", "priority": "high"}]
            )
        # Default: entity extraction for knowledge graph
        return json.dumps(
            {
                "entities": [
                    {"name": "Python", "type": "technology", "description": "Programming language"},
                    {"name": "Alice", "type": "person", "description": "Engineer"},
                ],
                "relationships": [
                    {"source": "Alice", "target": "Python", "type": "uses"},
                ],
            }
        )

    pm.chat.side_effect = _chat_side_effect
    pm.get_models_used.return_value = {"chat": "mock-gpt", "transcription": "mock-whisper"}
    return pm


def _make_tqdm_passthrough(mock_tqdm):
    """Configure mock tqdm to pass through iterables while supporting .set_description() etc."""

    def _tqdm_side_effect(iterable, **kw):
        wrapper = MagicMock()
        wrapper.__iter__ = lambda self: iter(iterable)
        return wrapper

    mock_tqdm.side_effect = _tqdm_side_effect


def _create_fake_video(path: Path) -> Path:
    """Create a tiny file that stands in for a video (all extractors are mocked)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * 64)
    return path


class TestProcessSingleVideo:
    """Integration-level tests for process_single_video with heavy mocking."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Create fake video, output dir, and mock PM."""
        video_path = _create_fake_video(tmp_path / "input" / "meeting.mp4")
        output_dir = tmp_path / "output"
        pm = _make_mock_pm()
        return video_path, output_dir, pm

    @patch("video_processor.pipeline.export_all_formats")
    @patch("video_processor.pipeline.PlanGenerator")
    @patch("video_processor.pipeline.DiagramAnalyzer")
    @patch("video_processor.pipeline.AudioExtractor")
    @patch("video_processor.pipeline.filter_people_frames")
    @patch("video_processor.pipeline.save_frames")
    @patch("video_processor.pipeline.extract_frames")
    @patch("video_processor.pipeline.tqdm")
    def test_returns_manifest(
        self,
        mock_tqdm,
        mock_extract_frames,
        mock_save_frames,
        mock_filter_people,
        mock_audio_extractor_cls,
        mock_diagram_analyzer_cls,
        mock_plan_gen_cls,
        mock_export,
        setup,
    ):
        video_path, output_dir, pm = setup

        # tqdm pass-through
        _make_tqdm_passthrough(mock_tqdm)

        # Frame extraction mocks
        mock_extract_frames.return_value = [b"fake_frame_1", b"fake_frame_2"]
        mock_filter_people.return_value = ([b"fake_frame_1", b"fake_frame_2"], 0)

        frames_dir = output_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        frame_paths = []
        for i in range(2):
            fp = frames_dir / f"frame_{i:04d}.jpg"
            fp.write_bytes(b"\xff")
            frame_paths.append(fp)
        mock_save_frames.return_value = frame_paths

        # Audio extractor mock
        audio_ext = MagicMock()
        audio_ext.extract_audio.return_value = output_dir / "audio" / "meeting.wav"
        audio_ext.get_audio_properties.return_value = {"duration": 10.0}
        mock_audio_extractor_cls.return_value = audio_ext

        # Diagram analyzer mock
        diag_analyzer = MagicMock()
        diag_analyzer.process_frames.return_value = ([], [])
        mock_diagram_analyzer_cls.return_value = diag_analyzer

        # Plan generator mock
        plan_gen = MagicMock()
        mock_plan_gen_cls.return_value = plan_gen

        # export_all_formats returns the manifest it receives
        mock_export.side_effect = lambda out_dir, manifest: manifest

        manifest = process_single_video(
            input_path=video_path,
            output_dir=output_dir,
            provider_manager=pm,
            depth="standard",
        )

        from video_processor.models import VideoManifest

        assert isinstance(manifest, VideoManifest)
        assert manifest.video.title == "Analysis of meeting"
        assert manifest.stats.frames_extracted == 2
        assert manifest.transcript_json == "transcript/transcript.json"
        assert manifest.knowledge_graph_json == "results/knowledge_graph.json"

        usage = json.loads((output_dir / "usage.json").read_text())
        for key in ("input_tokens", "output_tokens", "audio_minutes", "models", "steps"):
            assert key in usage

    @patch("video_processor.pipeline.export_all_formats")
    @patch("video_processor.pipeline.PlanGenerator")
    @patch("video_processor.pipeline.DiagramAnalyzer")
    @patch("video_processor.pipeline.AudioExtractor")
    @patch("video_processor.pipeline.filter_people_frames")
    @patch("video_processor.pipeline.save_frames")
    @patch("video_processor.pipeline.extract_frames")
    @patch("video_processor.pipeline.tqdm")
    def test_creates_output_directories(
        self,
        mock_tqdm,
        mock_extract_frames,
        mock_save_frames,
        mock_filter_people,
        mock_audio_extractor_cls,
        mock_diagram_analyzer_cls,
        mock_plan_gen_cls,
        mock_export,
        setup,
    ):
        video_path, output_dir, pm = setup

        _make_tqdm_passthrough(mock_tqdm)
        mock_extract_frames.return_value = []
        mock_filter_people.return_value = ([], 0)
        mock_save_frames.return_value = []

        audio_ext = MagicMock()
        audio_ext.extract_audio.return_value = output_dir / "audio" / "meeting.wav"
        audio_ext.get_audio_properties.return_value = {"duration": 5.0}
        mock_audio_extractor_cls.return_value = audio_ext

        diag_analyzer = MagicMock()
        diag_analyzer.process_frames.return_value = ([], [])
        mock_diagram_analyzer_cls.return_value = diag_analyzer

        plan_gen = MagicMock()
        mock_plan_gen_cls.return_value = plan_gen

        mock_export.side_effect = lambda out_dir, manifest: manifest

        process_single_video(
            input_path=video_path,
            output_dir=output_dir,
            provider_manager=pm,
        )

        # Verify standard output directories were created
        assert (output_dir / "transcript").is_dir()
        assert (output_dir / "frames").is_dir()
        assert (output_dir / "results").is_dir()

    @patch("video_processor.pipeline.export_all_formats")
    @patch("video_processor.pipeline.PlanGenerator")
    @patch("video_processor.pipeline.DiagramAnalyzer")
    @patch("video_processor.pipeline.AudioExtractor")
    @patch("video_processor.pipeline.filter_people_frames")
    @patch("video_processor.pipeline.save_frames")
    @patch("video_processor.pipeline.extract_frames")
    @patch("video_processor.pipeline.tqdm")
    def test_resume_existing_frames(
        self,
        mock_tqdm,
        mock_extract_frames,
        mock_save_frames,
        mock_filter_people,
        mock_audio_extractor_cls,
        mock_diagram_analyzer_cls,
        mock_plan_gen_cls,
        mock_export,
        setup,
    ):
        """When frames already exist on disk, extraction should be skipped."""
        video_path, output_dir, pm = setup

        _make_tqdm_passthrough(mock_tqdm)

        # Pre-create frames directory with existing frames
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            (frames_dir / f"frame_{i:04d}.jpg").write_bytes(b"\xff")

        audio_ext = MagicMock()
        audio_ext.extract_audio.return_value = output_dir / "audio" / "meeting.wav"
        audio_ext.get_audio_properties.return_value = {"duration": 10.0}
        mock_audio_extractor_cls.return_value = audio_ext

        diag_analyzer = MagicMock()
        diag_analyzer.process_frames.return_value = ([], [])
        mock_diagram_analyzer_cls.return_value = diag_analyzer

        plan_gen = MagicMock()
        mock_plan_gen_cls.return_value = plan_gen
        mock_export.side_effect = lambda out_dir, manifest: manifest

        manifest = process_single_video(
            input_path=video_path,
            output_dir=output_dir,
            provider_manager=pm,
        )

        # extract_frames should NOT have been called (resume path)
        mock_extract_frames.assert_not_called()
        assert manifest.stats.frames_extracted == 3

    @patch("video_processor.pipeline.export_all_formats")
    @patch("video_processor.pipeline.PlanGenerator")
    @patch("video_processor.pipeline.DiagramAnalyzer")
    @patch("video_processor.pipeline.AudioExtractor")
    @patch("video_processor.pipeline.filter_people_frames")
    @patch("video_processor.pipeline.save_frames")
    @patch("video_processor.pipeline.extract_frames")
    @patch("video_processor.pipeline.tqdm")
    def test_resume_existing_transcript(
        self,
        mock_tqdm,
        mock_extract_frames,
        mock_save_frames,
        mock_filter_people,
        mock_audio_extractor_cls,
        mock_diagram_analyzer_cls,
        mock_plan_gen_cls,
        mock_export,
        setup,
    ):
        """When transcript exists on disk, transcription should be skipped."""
        video_path, output_dir, pm = setup

        _make_tqdm_passthrough(mock_tqdm)
        mock_extract_frames.return_value = []
        mock_filter_people.return_value = ([], 0)
        mock_save_frames.return_value = []

        audio_ext = MagicMock()
        audio_ext.extract_audio.return_value = output_dir / "audio" / "meeting.wav"
        audio_ext.get_audio_properties.return_value = {"duration": 10.0}
        mock_audio_extractor_cls.return_value = audio_ext

        # Pre-create transcript file
        transcript_dir = output_dir / "transcript"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_data = {
            "text": "Pre-existing transcript text.",
            "segments": [{"start": 0.0, "end": 5.0, "text": "Pre-existing transcript text."}],
            "duration": 5.0,
        }
        (transcript_dir / "transcript.json").write_text(json.dumps(transcript_data))

        diag_analyzer = MagicMock()
        diag_analyzer.process_frames.return_value = ([], [])
        mock_diagram_analyzer_cls.return_value = diag_analyzer

        plan_gen = MagicMock()
        mock_plan_gen_cls.return_value = plan_gen
        mock_export.side_effect = lambda out_dir, manifest: manifest

        process_single_video(
            input_path=video_path,
            output_dir=output_dir,
            provider_manager=pm,
        )

        # transcribe_audio should NOT have been called (resume path)
        pm.transcribe_audio.assert_not_called()

    @patch("video_processor.pipeline.export_all_formats")
    @patch("video_processor.pipeline.PlanGenerator")
    @patch("video_processor.pipeline.DiagramAnalyzer")
    @patch("video_processor.pipeline.AudioExtractor")
    @patch("video_processor.pipeline.filter_people_frames")
    @patch("video_processor.pipeline.save_frames")
    @patch("video_processor.pipeline.extract_frames")
    @patch("video_processor.pipeline.tqdm")
    def test_custom_title(
        self,
        mock_tqdm,
        mock_extract_frames,
        mock_save_frames,
        mock_filter_people,
        mock_audio_extractor_cls,
        mock_diagram_analyzer_cls,
        mock_plan_gen_cls,
        mock_export,
        setup,
    ):
        video_path, output_dir, pm = setup

        _make_tqdm_passthrough(mock_tqdm)
        mock_extract_frames.return_value = []
        mock_filter_people.return_value = ([], 0)
        mock_save_frames.return_value = []

        audio_ext = MagicMock()
        audio_ext.extract_audio.return_value = output_dir / "audio" / "meeting.wav"
        audio_ext.get_audio_properties.return_value = {"duration": 5.0}
        mock_audio_extractor_cls.return_value = audio_ext

        diag_analyzer = MagicMock()
        diag_analyzer.process_frames.return_value = ([], [])
        mock_diagram_analyzer_cls.return_value = diag_analyzer

        plan_gen = MagicMock()
        mock_plan_gen_cls.return_value = plan_gen
        mock_export.side_effect = lambda out_dir, manifest: manifest

        manifest = process_single_video(
            input_path=video_path,
            output_dir=output_dir,
            provider_manager=pm,
            title="My Custom Title",
        )

        assert manifest.video.title == "My Custom Title"

    @patch("video_processor.pipeline.export_all_formats")
    @patch("video_processor.pipeline.PlanGenerator")
    @patch("video_processor.pipeline.DiagramAnalyzer")
    @patch("video_processor.pipeline.AudioExtractor")
    @patch("video_processor.pipeline.filter_people_frames")
    @patch("video_processor.pipeline.save_frames")
    @patch("video_processor.pipeline.extract_frames")
    @patch("video_processor.pipeline.tqdm")
    def test_key_points_and_action_items_extracted(
        self,
        mock_tqdm,
        mock_extract_frames,
        mock_save_frames,
        mock_filter_people,
        mock_audio_extractor_cls,
        mock_diagram_analyzer_cls,
        mock_plan_gen_cls,
        mock_export,
        setup,
    ):
        video_path, output_dir, pm = setup

        _make_tqdm_passthrough(mock_tqdm)
        mock_extract_frames.return_value = []
        mock_filter_people.return_value = ([], 0)
        mock_save_frames.return_value = []

        audio_ext = MagicMock()
        audio_ext.extract_audio.return_value = output_dir / "audio" / "meeting.wav"
        audio_ext.get_audio_properties.return_value = {"duration": 10.0}
        mock_audio_extractor_cls.return_value = audio_ext

        diag_analyzer = MagicMock()
        diag_analyzer.process_frames.return_value = ([], [])
        mock_diagram_analyzer_cls.return_value = diag_analyzer

        plan_gen = MagicMock()
        mock_plan_gen_cls.return_value = plan_gen
        mock_export.side_effect = lambda out_dir, manifest: manifest

        manifest = process_single_video(
            input_path=video_path,
            output_dir=output_dir,
            provider_manager=pm,
        )

        assert len(manifest.key_points) == 1
        assert manifest.key_points[0].point == "Deployment strategy discussed"
        assert len(manifest.action_items) == 1
        assert manifest.action_items[0].action == "Deploy to production"
