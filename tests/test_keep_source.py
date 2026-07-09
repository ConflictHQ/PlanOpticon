"""Tests for GoogleKeepSource: gws CLI wrapper, listing, and download.

Complements the constructor / no-gws-CLI / _note_to_text cases in
tests/test_sources.py by exercising _run_gws (subprocess boundary),
authenticate success/failure, list_videos result shapes, and download.
The gws CLI is not invoked for real -- subprocess.run / _run_gws are mocked.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from video_processor.sources.base import SourceFile


class TestRunGws:
    @patch("video_processor.sources.google_keep_source.subprocess.run")
    def test_run_gws_success_parses_json(self, mock_run):
        from video_processor.sources.google_keep_source import _run_gws

        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"notes": [{"id": "n1"}]}', stderr=""
        )
        result = _run_gws(["keep", "notes", "list"])

        assert result == {"notes": [{"id": "n1"}]}
        assert mock_run.call_args[0][0] == ["gws", "keep", "notes", "list"]

    @patch("video_processor.sources.google_keep_source.subprocess.run")
    def test_run_gws_nonzero_raises(self, mock_run):
        from video_processor.sources.google_keep_source import _run_gws

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="auth error")
        with pytest.raises(RuntimeError, match="auth error"):
            _run_gws(["auth", "status"])

    @patch("video_processor.sources.google_keep_source.subprocess.run")
    def test_run_gws_non_json_returns_raw(self, mock_run):
        from video_processor.sources.google_keep_source import _run_gws

        mock_run.return_value = MagicMock(returncode=0, stdout="plain text output", stderr="")
        result = _run_gws(["some", "command"])

        assert result == {"raw": "plain text output"}


class TestGoogleKeepAuthenticate:
    @patch("video_processor.sources.google_keep_source._run_gws")
    @patch("shutil.which", return_value="/usr/local/bin/gws")
    def test_authenticate_success(self, _which, mock_run):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.return_value = {"connectedAs": "user@example.com"}
        assert GoogleKeepSource().authenticate() is True

    @patch("video_processor.sources.google_keep_source._run_gws")
    @patch("shutil.which", return_value="/usr/local/bin/gws")
    def test_authenticate_gws_not_authed(self, _which, mock_run):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.side_effect = RuntimeError("not authenticated")
        assert GoogleKeepSource().authenticate() is False


class TestGoogleKeepListVideos:
    @patch("video_processor.sources.google_keep_source._run_gws")
    def test_list_videos_list_result(self, mock_run):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.return_value = [
            {
                "id": "n1",
                "title": "Meeting",
                "body": "notes body",
                "modifiedTime": "2026-01-01T00:00:00Z",
            },
            {"id": "n2", "title": "   ", "textContent": "untitled body"},
        ]
        files = GoogleKeepSource().list_videos()

        assert len(files) == 2
        assert files[0].name == "Meeting"
        assert files[0].id == "n1"
        assert files[0].mime_type == "text/plain"
        assert files[0].modified_at == "2026-01-01T00:00:00Z"
        assert files[0].size_bytes is not None and files[0].size_bytes > 0
        # Blank title falls back to "Untitled Note".
        assert files[1].name == "Untitled Note"

    @patch("video_processor.sources.google_keep_source._run_gws")
    def test_list_videos_passes_label(self, mock_run):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.return_value = []
        GoogleKeepSource(label="meetings").list_videos()

        passed = mock_run.call_args[0][0]
        assert "--label" in passed
        assert "meetings" in passed

    @patch("video_processor.sources.google_keep_source._run_gws")
    def test_list_videos_dict_items_key(self, mock_run):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.return_value = {"items": [{"noteId": "x1", "title": "From items"}]}
        files = GoogleKeepSource().list_videos()

        assert len(files) == 1
        assert files[0].id == "x1"  # noteId fallback
        assert files[0].name == "From items"

    @patch("video_processor.sources.google_keep_source._run_gws")
    def test_list_videos_single_note_dict(self, mock_run):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.return_value = {"id": "single1", "title": "Single", "body": "content"}
        files = GoogleKeepSource().list_videos()

        assert len(files) == 1
        assert files[0].id == "single1"
        assert files[0].name == "Single"

    @patch("video_processor.sources.google_keep_source._run_gws")
    def test_list_videos_error_returns_empty(self, mock_run):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.side_effect = RuntimeError("gws failed")
        assert GoogleKeepSource().list_videos() == []


class TestGoogleKeepDownload:
    @patch("video_processor.sources.google_keep_source._run_gws")
    def test_download_writes_note(self, mock_run, tmp_path):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.return_value = {
            "title": "My Note",
            "body": "Line one",
            "listContent": [{"text": "todo", "checked": False}],
        }
        f = SourceFile(name="My Note", id="note123", mime_type="text/plain")
        dest = tmp_path / "notes" / "note.txt"

        result = GoogleKeepSource().download(f, dest)

        assert result == dest
        content = dest.read_text()
        assert "My Note" in content
        assert "Line one" in content
        assert "- [ ] todo" in content
        # noteId is threaded through to the gws call params.
        assert "note123" in json.dumps(mock_run.call_args[0][0])

    @patch("video_processor.sources.google_keep_source._run_gws")
    def test_download_error_raises(self, mock_run, tmp_path):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.side_effect = RuntimeError("fetch failed")
        f = SourceFile(name="X", id="n1")

        with pytest.raises(RuntimeError, match="Failed to fetch Keep note"):
            GoogleKeepSource().download(f, tmp_path / "x.txt")

    @patch("video_processor.sources.google_keep_source._run_gws")
    def test_download_empty_text_falls_back_to_raw(self, mock_run, tmp_path):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.return_value = {"raw": "unstructured content"}
        f = SourceFile(name="Raw", id="n1")
        dest = tmp_path / "raw.txt"

        GoogleKeepSource().download(f, dest)

        assert dest.read_text() == "unstructured content"

    @patch("video_processor.sources.google_keep_source._run_gws")
    def test_download_empty_text_falls_back_to_json(self, mock_run, tmp_path):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.return_value = {"unexpected": "shape"}
        f = SourceFile(name="Odd", id="n1")
        dest = tmp_path / "odd.txt"

        GoogleKeepSource().download(f, dest)

        # No extractable text and no raw key => JSON dump of the note.
        assert "unexpected" in dest.read_text()

    @patch("video_processor.sources.google_keep_source._run_gws")
    def test_download_non_dict_result(self, mock_run, tmp_path):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        mock_run.return_value = ["not", "a", "dict"]
        f = SourceFile(name="Listy", id="n1")
        dest = tmp_path / "listy.txt"

        GoogleKeepSource().download(f, dest)

        # Non-dict result => note treated as {} => JSON dump "{}".
        assert dest.read_text() == "{}"
