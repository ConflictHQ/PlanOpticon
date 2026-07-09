"""Tests for AppleNotesSource: osascript listing, parsing, and download.

Complements the constructor / authenticate-platform / _html_to_text cases in
tests/test_sources.py by exercising list_videos (both folder scripts and the
error branches), _parse_note_list, and download. osascript is never actually
invoked -- subprocess.run and sys.platform are patched so the suite is
deterministic on any OS.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from video_processor.sources.base import SourceFile

_DARWIN = patch("video_processor.sources.apple_notes_source.sys.platform", "darwin")


class TestAppleNotesAuthenticate:
    def test_authenticate_non_darwin(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        with patch("video_processor.sources.apple_notes_source.sys.platform", "linux"):
            assert AppleNotesSource().authenticate() is False


class TestAppleNotesListVideos:
    def test_list_videos_non_darwin_returns_empty(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        with patch("video_processor.sources.apple_notes_source.sys.platform", "linux"):
            assert AppleNotesSource().list_videos() == []

    @patch("video_processor.sources.apple_notes_source.subprocess.run")
    def test_list_videos_default_account(self, mock_run):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="x-coredata://1/p1|||First Note, x-coredata://2/p2|||Second Note",
            stderr="",
        )
        with _DARWIN:
            files = AppleNotesSource().list_videos()

        assert len(files) == 2
        assert files[0].name == "First Note"
        assert files[0].id == "x-coredata://1/p1"
        assert files[0].mime_type == "text/plain"
        assert files[1].name == "Second Note"
        # The default-account script (no folder filter) was used.
        script = mock_run.call_args[0][0][2]
        assert "notes of default account" in script

    @patch("video_processor.sources.apple_notes_source.subprocess.run")
    def test_list_videos_with_folder(self, mock_run):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        mock_run.return_value = MagicMock(returncode=0, stdout="id1|||Note A", stderr="")
        with _DARWIN:
            files = AppleNotesSource(folder="Work").list_videos()

        assert len(files) == 1
        assert files[0].name == "Note A"
        # The folder-scoped script names the requested folder.
        script = mock_run.call_args[0][0][2]
        assert 'name of f is "Work"' in script

    @patch(
        "video_processor.sources.apple_notes_source.subprocess.run",
        side_effect=FileNotFoundError,
    )
    def test_list_videos_osascript_missing(self, _mock_run):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        with _DARWIN:
            assert AppleNotesSource().list_videos() == []

    @patch(
        "video_processor.sources.apple_notes_source.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=30),
    )
    def test_list_videos_timeout(self, _mock_run):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        with _DARWIN:
            assert AppleNotesSource().list_videos() == []

    @patch("video_processor.sources.apple_notes_source.subprocess.run")
    def test_list_videos_nonzero_return(self, mock_run):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="permission denied")
        with _DARWIN:
            assert AppleNotesSource().list_videos() == []


class TestAppleNotesParseNoteList:
    def test_parse_basic(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        files = AppleNotesSource()._parse_note_list("id1|||Alpha, id2|||Beta")

        assert [f.id for f in files] == ["id1", "id2"]
        assert [f.name for f in files] == ["Alpha", "Beta"]
        assert all(f.mime_type == "text/plain" for f in files)

    def test_parse_empty(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        assert AppleNotesSource()._parse_note_list("") == []

    def test_parse_skips_malformed_entries(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        files = AppleNotesSource()._parse_note_list("garbage without separator, id9|||Valid")

        assert len(files) == 1
        assert files[0].name == "Valid"

    def test_parse_skips_empty_fields(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        # "|||NoId" has an empty id; "idNoName|||" has an empty name -> both dropped.
        files = AppleNotesSource()._parse_note_list("|||NoId, idNoName|||")

        assert files == []


class TestAppleNotesDownload:
    @patch("video_processor.sources.apple_notes_source.subprocess.run")
    def test_download_writes_note(self, mock_run, tmp_path):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="<div>Hello <b>World</b></div><p>Second line.</p>",
            stderr="",
        )
        f = SourceFile(name="My Note", id="x-coredata://1/note1", mime_type="text/plain")
        dest = tmp_path / "notes" / "note.txt"

        result = AppleNotesSource().download(f, dest)

        assert result == dest
        content = dest.read_text()
        assert content.startswith("# My Note")
        assert "Hello World" in content
        assert "Second line." in content
        # The note id is embedded in the AppleScript body request.
        assert "x-coredata://1/note1" in mock_run.call_args[0][0][2]

    @patch(
        "video_processor.sources.apple_notes_source.subprocess.run",
        side_effect=FileNotFoundError,
    )
    def test_download_osascript_missing(self, _mock_run, tmp_path):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        f = SourceFile(name="N", id="id1")
        with pytest.raises(RuntimeError, match="osascript not found"):
            AppleNotesSource().download(f, tmp_path / "n.txt")

    @patch(
        "video_processor.sources.apple_notes_source.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=30),
    )
    def test_download_timeout(self, _mock_run, tmp_path):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        f = SourceFile(name="N", id="id1")
        with pytest.raises(RuntimeError, match="timed out"):
            AppleNotesSource().download(f, tmp_path / "n.txt")

    @patch("video_processor.sources.apple_notes_source.subprocess.run")
    def test_download_nonzero_return(self, mock_run, tmp_path):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="no such note")
        f = SourceFile(name="N", id="id1")
        with pytest.raises(RuntimeError, match="Failed to fetch note"):
            AppleNotesSource().download(f, tmp_path / "n.txt")
