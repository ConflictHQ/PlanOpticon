"""Tests for the Google Meet recording source.

The Meet source shells out to the ``gws`` CLI via ``_run_gws`` (imported into the
module namespace) and probes ``shutil.which``. Those are the external boundaries,
so they are the only things patched. Downloads are written to real ``tmp_path``
files and read back.
"""

import json
import subprocess
from unittest.mock import patch

from video_processor.sources.base import SourceFile
from video_processor.sources.meet_recording_source import MeetRecordingSource

_RUN_GWS = "video_processor.sources.meet_recording_source._run_gws"


class TestMeetConstruction:
    def test_defaults(self):
        src = MeetRecordingSource()
        assert src.drive_folder_id is None

    def test_with_folder(self):
        src = MeetRecordingSource(drive_folder_id="folder123")
        assert src.drive_folder_id == "folder123"


class TestMeetAuthenticate:
    @patch("shutil.which", return_value=None)
    def test_no_gws_cli_returns_false(self, _mock_which):
        src = MeetRecordingSource()
        assert src.authenticate() is False

    @patch(_RUN_GWS)
    @patch("shutil.which", return_value="/usr/local/bin/gws")
    def test_success(self, _mock_which, mock_run):
        mock_run.return_value = {"connectedAs": "me@example.com"}
        src = MeetRecordingSource()
        assert src.authenticate() is True
        assert mock_run.call_args.args[0] == ["auth", "status"]

    @patch(_RUN_GWS, side_effect=RuntimeError("not logged in"))
    @patch("shutil.which", return_value="/usr/local/bin/gws")
    def test_runtime_error_returns_false(self, _mock_which, _mock_run):
        src = MeetRecordingSource()
        assert src.authenticate() is False

    @patch(_RUN_GWS, side_effect=subprocess.TimeoutExpired(cmd="gws", timeout=10))
    @patch("shutil.which", return_value="/usr/local/bin/gws")
    def test_timeout_returns_false(self, _mock_which, _mock_run):
        src = MeetRecordingSource()
        assert src.authenticate() is False


class TestMeetListVideos:
    @patch(_RUN_GWS)
    def test_success_with_constructor_folder(self, mock_run):
        mock_run.side_effect = [
            {
                "files": [
                    {
                        "id": "r1",
                        "name": "Meet Recording 2026-03-07",
                        "mimeType": "video/mp4",
                        "size": "2048",
                        "modifiedTime": "2026-03-07T00:00:00Z",
                    },
                    {"id": "r2", "name": "Meet Recording 2026-03-08"},
                ]
            },
            {"files": [{"id": "t1", "name": "Transcript 2026-03-07"}]},
        ]
        src = MeetRecordingSource(drive_folder_id="folderX")
        files = src.list_videos()
        assert len(files) == 2
        assert files[0].id == "r1"
        assert files[0].name == "Meet Recording 2026-03-07"
        assert files[0].size_bytes == 2048
        assert files[0].mime_type == "video/mp4"
        assert files[0].modified_at == "2026-03-07T00:00:00Z"
        assert files[1].size_bytes is None
        assert files[1].mime_type == "video/mp4"
        params = json.loads(mock_run.call_args_list[0].args[0][4])
        assert "'folderX' in parents" in params["q"]

    @patch(_RUN_GWS)
    def test_success_with_folder_param(self, mock_run):
        mock_run.side_effect = [
            {"files": [{"id": "r1", "name": "Meet Recording 2026-03-07"}]},
            {"files": []},
        ]
        src = MeetRecordingSource()
        files = src.list_videos(folder_id="paramFolder")
        assert len(files) == 1
        params = json.loads(mock_run.call_args_list[0].args[0][4])
        assert "'paramFolder' in parents" in params["q"]

    @patch(_RUN_GWS, side_effect=RuntimeError("drive down"))
    def test_recordings_query_error_returns_empty(self, mock_run):
        src = MeetRecordingSource()
        assert src.list_videos() == []
        assert mock_run.call_count == 1

    @patch(_RUN_GWS)
    def test_transcript_query_error_still_returns_recordings(self, mock_run):
        mock_run.side_effect = [
            {"files": [{"id": "r1", "name": "Meet Recording 2026-03-07"}]},
            RuntimeError("transcript query failed"),
        ]
        src = MeetRecordingSource()
        files = src.list_videos()
        assert len(files) == 1
        assert mock_run.call_count == 2

    @patch(_RUN_GWS)
    def test_no_recordings_found_returns_empty(self, mock_run):
        mock_run.side_effect = [{"files": []}, {"files": []}]
        src = MeetRecordingSource()
        assert src.list_videos() == []


class TestMeetDownload:
    @patch(_RUN_GWS)
    def test_success_dict_raw(self, mock_run, tmp_path):
        mock_run.return_value = {"raw": "video-content"}
        src = MeetRecordingSource()
        f = SourceFile(name="rec.mp4", id="r1")
        dest = tmp_path / "sub" / "rec.mp4"
        result = src.download(f, dest)
        assert result == dest
        assert dest.read_text() == "video-content"
        params = json.loads(mock_run.call_args.args[0][4])
        assert params["fileId"] == "r1"
        assert params["alt"] == "media"

    @patch(_RUN_GWS)
    def test_non_dict_result_is_stringified(self, mock_run, tmp_path):
        mock_run.return_value = "plain-content"
        src = MeetRecordingSource()
        f = SourceFile(name="rec.mp4", id="r1")
        dest = tmp_path / "rec.mp4"
        src.download(f, dest)
        assert dest.read_text() == "plain-content"

    @patch(_RUN_GWS)
    def test_dict_without_raw_writes_empty(self, mock_run, tmp_path):
        mock_run.return_value = {"unexpected": "x"}
        src = MeetRecordingSource()
        f = SourceFile(name="rec.mp4", id="r1")
        dest = tmp_path / "rec.mp4"
        src.download(f, dest)
        assert dest.read_text() == ""


class TestMeetFetchTranscript:
    @patch(_RUN_GWS)
    def test_success_extracts_text(self, mock_run):
        mock_run.side_effect = [
            {"files": [{"id": "doc1", "name": "Transcript 2026-03-07"}]},
            {
                "body": {
                    "content": [
                        {"paragraph": {"elements": [{"textRun": {"content": "Hello world\n"}}]}},
                        {"paragraph": {"elements": [{"textRun": {"content": "Second line\n"}}]}},
                    ]
                }
            },
        ]
        src = MeetRecordingSource()
        text = src.fetch_transcript("Meet Recording 2026-03-07")
        assert text == "Hello world\nSecond line\n"
        assert mock_run.call_count == 2

    @patch(_RUN_GWS)
    def test_no_matching_transcript_returns_none(self, mock_run):
        mock_run.side_effect = [{"files": []}]
        src = MeetRecordingSource()
        assert src.fetch_transcript("Meet Recording 2026-03-07") is None
        assert mock_run.call_count == 1

    @patch(_RUN_GWS, side_effect=RuntimeError("search failed"))
    def test_find_transcript_error_returns_none(self, _mock_run):
        src = MeetRecordingSource()
        assert src.fetch_transcript("Meet Recording 2026-03-07") is None

    @patch(_RUN_GWS)
    def test_docs_fetch_error_returns_none(self, mock_run):
        mock_run.side_effect = [
            {"files": [{"id": "doc1", "name": "Transcript 2026-03-07"}]},
            RuntimeError("docs api down"),
        ]
        src = MeetRecordingSource()
        assert src.fetch_transcript("Meet Recording 2026-03-07") is None

    @patch(_RUN_GWS)
    def test_no_extractable_text_returns_none(self, mock_run):
        mock_run.side_effect = [
            {"files": [{"id": "doc1", "name": "Transcript 2026-03-07"}]},
            {
                "body": {
                    "content": [
                        {"paragraph": {"elements": [{"textRun": {"content": "   \n"}}]}},
                    ]
                }
            },
        ]
        src = MeetRecordingSource()
        assert src.fetch_transcript("Meet Recording 2026-03-07") is None


class TestMeetFindMatchingTranscript:
    @patch(_RUN_GWS)
    def test_match_returns_id_and_uses_date(self, mock_run):
        mock_run.return_value = {"files": [{"id": "doc9", "name": "T"}]}
        src = MeetRecordingSource()
        assert src._find_matching_transcript("Meet Recording 2026-03-07") == "doc9"
        query = json.loads(mock_run.call_args.args[0][4])["q"]
        assert "2026-03-07" in query

    @patch(_RUN_GWS)
    def test_no_date_falls_back_to_full_name(self, mock_run):
        mock_run.return_value = {"files": []}
        src = MeetRecordingSource()
        assert src._find_matching_transcript("NoDateRecording") is None
        query = json.loads(mock_run.call_args.args[0][4])["q"]
        assert "NoDateRecording" in query

    @patch(_RUN_GWS, side_effect=RuntimeError("boom"))
    def test_runtime_error_returns_none(self, _mock_run):
        src = MeetRecordingSource()
        assert src._find_matching_transcript("2026-03-07") is None

    @patch(_RUN_GWS)
    def test_folder_id_scopes_query(self, mock_run):
        mock_run.return_value = {"files": [{"id": "doc1", "name": "T"}]}
        src = MeetRecordingSource(drive_folder_id="FID")
        src._find_matching_transcript("2026-03-07")
        query = json.loads(mock_run.call_args.args[0][4])["q"]
        assert "'FID' in parents" in query
