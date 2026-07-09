"""Tests for the Microsoft Teams meeting-recording source.

Like the M365 source, this connector reaches Microsoft Graph through the `m365`
CLI (via the shared ``_run_m365`` helper), not the ``requests`` library. The only
mocked boundary is ``_run_m365`` (imported into this module's namespace) and
``shutil.which`` for authentication. Real files land in ``tmp_path``.
"""

import subprocess
from unittest.mock import patch

from video_processor.sources.base import SourceFile
from video_processor.sources.teams_recording_source import (
    TeamsRecordingSource,
    _vtt_to_text,
)

TEAMS = "video_processor.sources.teams_recording_source"


class TestVttToText:
    def test_strips_metadata_and_tags(self):
        vtt = (
            "WEBVTT\n\n"
            "NOTE This is a note\n\n"
            "1\n"
            "00:00:01.000 --> 00:00:05.000\n"
            "<v Alice>Hello everyone\n\n"
            "2\n"
            "00:00:05.000 --> 00:00:09.000\n"
            "<v Bob>Good morning\n"
        )
        assert _vtt_to_text(vtt) == "Hello everyone\nGood morning"

    def test_empty_input(self):
        assert _vtt_to_text("") == ""

    def test_deduplicates_consecutive_lines(self):
        vtt = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:03.000\nSame line\n\n"
            "00:00:03.000 --> 00:00:05.000\nSame line\n"
        )
        assert _vtt_to_text(vtt).count("Same line") == 1

    def test_removes_headers_and_notes(self):
        vtt = "WEBVTT\nNOTE meta\n00:00:00.000 --> 00:00:01.000\nActual words\n"
        result = _vtt_to_text(vtt)
        assert result == "Actual words"
        assert "WEBVTT" not in result
        assert "NOTE" not in result


class TestTeamsConstructor:
    def test_default_user(self):
        assert TeamsRecordingSource().user_id == "me"

    def test_custom_user(self):
        assert TeamsRecordingSource(user_id="user@example.com").user_id == "user@example.com"


class TestTeamsAuthenticate:
    @patch(f"{TEAMS}.shutil.which", return_value=None)
    def test_cli_not_installed(self, _which):
        assert TeamsRecordingSource().authenticate() is False

    @patch(f"{TEAMS}._run_m365")
    @patch(f"{TEAMS}.shutil.which", return_value="/usr/local/bin/m365")
    def test_connected_dict(self, _which, mock_run):
        mock_run.return_value = {"connectedAs": "user@contoso.com"}
        assert TeamsRecordingSource().authenticate() is True

    @patch(f"{TEAMS}._run_m365")
    @patch(f"{TEAMS}.shutil.which", return_value="/usr/local/bin/m365")
    def test_logged_in_string(self, _which, mock_run):
        mock_run.return_value = "Logged in as someone"
        assert TeamsRecordingSource().authenticate() is True

    @patch(f"{TEAMS}._run_m365")
    @patch(f"{TEAMS}.shutil.which", return_value="/usr/local/bin/m365")
    def test_not_logged_in(self, _which, mock_run):
        mock_run.return_value = {}
        assert TeamsRecordingSource().authenticate() is False

    @patch(f"{TEAMS}._run_m365")
    @patch(f"{TEAMS}.shutil.which", return_value="/usr/local/bin/m365")
    def test_runtime_error_returns_false(self, _which, mock_run):
        mock_run.side_effect = RuntimeError("status failed")
        assert TeamsRecordingSource().authenticate() is False

    @patch(f"{TEAMS}._run_m365")
    @patch(f"{TEAMS}.shutil.which", return_value="/usr/local/bin/m365")
    def test_timeout_returns_false(self, _which, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("m365", 10)
        assert TeamsRecordingSource().authenticate() is False


class TestTeamsListVideos:
    @patch(f"{TEAMS}._run_m365")
    def test_approach1_online_meetings(self, mock_run):
        mock_run.side_effect = [
            # onlineMeetings listing
            {
                "value": [
                    {"id": "m1", "subject": "Standup", "startDateTime": "2026-01-01T09:00:00Z"}
                ]
            },
            # recordings for m1
            {"value": [{"id": "rec1", "content.downloadUrl": "https://dl/rec1"}]},
        ]
        files = TeamsRecordingSource().list_videos()
        assert len(files) == 1
        assert files[0].name == "Standup.mp4"
        assert files[0].id == "m1:rec1"
        assert files[0].path == "https://dl/rec1"
        assert files[0].mime_type == "video/mp4"
        assert files[0].modified_at == "2026-01-01T09:00:00Z"

    @patch(f"{TEAMS}._run_m365")
    def test_approach2_teams_meeting_list(self, mock_run):
        mock_run.side_effect = [
            RuntimeError("onlineMeetings 404"),  # approach 1 fails
            [{"id": "m2", "topic": "Retro", "createdDateTime": "2026-02-02T10:00:00Z"}],
            {"value": [{"id": "rec2", "contentUrl": "https://dl/rec2"}]},  # recordings for m2
        ]
        files = TeamsRecordingSource().list_videos()
        assert len(files) == 1
        assert files[0].name == "Retro.mp4"
        assert files[0].id == "m2:rec2"
        # contentUrl is used when content.downloadUrl is absent.
        assert files[0].path == "https://dl/rec2"
        assert files[0].modified_at == "2026-02-02T10:00:00Z"

    @patch(f"{TEAMS}._run_m365")
    def test_approach3_chat_recording_links(self, mock_run):
        mock_run.side_effect = [
            {"value": []},  # approach 1: no meetings
            [],  # approach 2: no meetings
            {  # approach 3: chats with messages
                "value": [
                    {
                        "id": "chat1",
                        "topic": "Project Sync",
                        "messages": [
                            {
                                "id": "msg1",
                                "createdDateTime": "2026-03-03T00:00:00Z",
                                "body": {"content": "Here is the recording of our call"},
                            },
                            {"id": "msg2", "body": {"content": "no link here"}},
                        ],
                    }
                ]
            },
        ]
        files = TeamsRecordingSource().list_videos()
        assert len(files) == 1
        assert files[0].name == "Project Sync.mp4"
        assert files[0].id == "chat1:msg1"
        assert files[0].mime_type == "video/mp4"
        assert files[0].modified_at == "2026-03-03T00:00:00Z"

    @patch(f"{TEAMS}._run_m365")
    def test_no_recordings_found(self, mock_run):
        mock_run.side_effect = [
            {"value": []},
            [],
            {"value": []},
        ]
        assert TeamsRecordingSource().list_videos() == []

    @patch(f"{TEAMS}._run_m365")
    def test_all_approaches_error(self, mock_run):
        mock_run.side_effect = RuntimeError("everything fails")
        assert TeamsRecordingSource().list_videos() == []


class TestTeamsDownload:
    @patch(f"{TEAMS}._run_m365")
    def test_download_with_direct_url(self, mock_run, tmp_path):
        src = TeamsRecordingSource()
        f = SourceFile(name="Standup.mp4", id="m1:rec1", path="https://dl/rec1")
        dest = tmp_path / "out" / "Standup.mp4"
        result = src.download(f, dest)
        assert result == dest
        assert dest.parent.is_dir()  # real mkdir happened
        args = mock_run.call_args[0][0]
        assert "https://dl/rec1" in args
        assert "--filePath" in args and str(dest) in args

    @patch(f"{TEAMS}._run_m365")
    def test_download_with_recording_id(self, mock_run, tmp_path):
        src = TeamsRecordingSource(user_id="user@example.com")
        f = SourceFile(name="Standup.mp4", id="m1:rec1")  # no path
        dest = tmp_path / "Standup.mp4"
        src.download(f, dest)
        args = mock_run.call_args[0][0]
        url = args[args.index("--url") + 1]
        assert url == (
            "https://graph.microsoft.com/v1.0/user@example.com"
            "/onlineMeetings/m1/recordings/rec1/content"
        )

    @patch(f"{TEAMS}._run_m365")
    def test_download_resolves_recording_list(self, mock_run, tmp_path):
        # id with no recording part -> fetch recordings list, use the first entry.
        mock_run.side_effect = [
            {"value": [{"id": "recX"}]},  # recordings listing
            None,  # the content download call
        ]
        src = TeamsRecordingSource()
        f = SourceFile(name="Meeting.mp4", id="m9")
        src.download(f, tmp_path / "Meeting.mp4")
        download_args = mock_run.call_args_list[1][0][0]
        url = download_args[download_args.index("--url") + 1]
        assert url.endswith("/onlineMeetings/m9/recordings/recX/content")

    @patch(f"{TEAMS}._run_m365")
    def test_download_empty_recording_list(self, mock_run, tmp_path):
        mock_run.side_effect = [
            {"value": []},  # no recordings resolved
            None,  # download call
        ]
        src = TeamsRecordingSource()
        f = SourceFile(name="Meeting.mp4", id="m9:")  # trailing colon -> empty rec id
        src.download(f, tmp_path / "Meeting.mp4")
        download_args = mock_run.call_args_list[1][0][0]
        url = download_args[download_args.index("--url") + 1]
        assert url.endswith("/onlineMeetings/m9/recordings")


class TestTeamsFetchTranscript:
    @patch(f"{TEAMS}._run_m365")
    def test_success_raw_vtt_string(self, mock_run):
        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<v Alice>Hello team\n"
        mock_run.side_effect = [
            {"value": [{"id": "t1"}]},  # transcripts listing
            vtt,  # transcript content
        ]
        assert TeamsRecordingSource().fetch_transcript("m1") == "Hello team"

    @patch(f"{TEAMS}._run_m365")
    def test_success_dict_with_raw_key(self, mock_run):
        mock_run.side_effect = [
            {"value": [{"id": "t1"}]},
            {"raw": "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nWord\n"},
        ]
        assert TeamsRecordingSource().fetch_transcript("m1") == "Word"

    @patch(f"{TEAMS}._run_m365")
    def test_transcript_list_error_returns_none(self, mock_run):
        mock_run.side_effect = RuntimeError("list failed")
        assert TeamsRecordingSource().fetch_transcript("m1") is None

    @patch(f"{TEAMS}._run_m365")
    def test_no_transcripts_returns_none(self, mock_run):
        mock_run.return_value = {"value": []}
        assert TeamsRecordingSource().fetch_transcript("m1") is None

    @patch(f"{TEAMS}._run_m365")
    def test_content_download_error_returns_none(self, mock_run):
        mock_run.side_effect = [
            {"value": [{"id": "t1"}]},
            RuntimeError("content failed"),
        ]
        assert TeamsRecordingSource().fetch_transcript("m1") is None

    @patch(f"{TEAMS}._run_m365")
    def test_empty_content_returns_none(self, mock_run):
        mock_run.side_effect = [
            {"value": [{"id": "t1"}]},
            "",  # empty transcript body
        ]
        assert TeamsRecordingSource().fetch_transcript("m1") is None


class TestTeamsExtractHelpers:
    def test_extract_meetings_list_from_dict(self):
        src = TeamsRecordingSource()
        assert src._extract_meetings_list({"value": [{"id": "m1"}]}) == [{"id": "m1"}]

    def test_extract_meetings_list_from_list(self):
        src = TeamsRecordingSource()
        assert src._extract_meetings_list([{"id": "m1"}]) == [{"id": "m1"}]

    def test_extract_meetings_list_other_returns_empty(self):
        assert TeamsRecordingSource()._extract_meetings_list("nope") == []

    def test_extract_value_list_from_dict(self):
        assert TeamsRecordingSource()._extract_value_list({"value": [1, 2]}) == [1, 2]

    def test_extract_value_list_from_list(self):
        assert TeamsRecordingSource()._extract_value_list([1, 2]) == [1, 2]

    def test_extract_value_list_other_returns_empty(self):
        assert TeamsRecordingSource()._extract_value_list(None) == []


class TestTeamsGetMeetingRecordings:
    @patch(f"{TEAMS}._run_m365")
    def test_builds_source_files(self, mock_run):
        mock_run.return_value = {
            "value": [
                {"id": "rec1", "content.downloadUrl": "https://dl/1"},
                {"id": "rec2", "contentUrl": "https://dl/2"},
            ]
        }
        meeting = {"id": "m1", "subject": "Planning", "startDateTime": "2026-01-01T00:00:00Z"}
        files = TeamsRecordingSource()._get_meeting_recordings(meeting)
        assert len(files) == 2
        assert files[0].name == "Planning.mp4"
        assert files[0].id == "m1:rec1"
        assert files[0].path == "https://dl/1"
        assert files[0].modified_at == "2026-01-01T00:00:00Z"
        assert files[1].id == "m1:rec2"
        assert files[1].path == "https://dl/2"  # contentUrl fallback

    def test_missing_meeting_id_returns_empty(self):
        assert TeamsRecordingSource()._get_meeting_recordings({}) == []

    @patch(f"{TEAMS}._run_m365")
    def test_recordings_error_returns_empty(self, mock_run):
        mock_run.side_effect = RuntimeError("recordings 404")
        assert TeamsRecordingSource()._get_meeting_recordings({"id": "m1", "subject": "X"}) == []

    @patch(f"{TEAMS}._run_m365")
    def test_topic_and_created_fallbacks(self, mock_run):
        mock_run.return_value = {"value": [{"id": "rec1"}]}
        # No subject -> topic; no startDateTime -> createdDateTime; no url keys -> path None.
        meeting = {"id": "m1", "topic": "Weekly", "createdDateTime": "2026-05-05T00:00:00Z"}
        files = TeamsRecordingSource()._get_meeting_recordings(meeting)
        assert files[0].name == "Weekly.mp4"
        assert files[0].modified_at == "2026-05-05T00:00:00Z"
        assert files[0].path is None

    @patch(f"{TEAMS}._run_m365")
    def test_default_subject(self, mock_run):
        mock_run.return_value = {"value": [{"id": "rec1"}]}
        files = TeamsRecordingSource()._get_meeting_recordings({"id": "m1"})
        assert files[0].name == "Teams Meeting.mp4"
