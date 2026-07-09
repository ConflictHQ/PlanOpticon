"""Tests for DropboxSource: auth flows, listing, and download.

Complements the constructor / not-authenticated / auth-no-sdk / saved-token
cases already covered in tests/test_cloud_sources.py by exercising the
untested access-token auth, OAuth flow, list_videos, and download paths.
The dropbox SDK is installed, so real ``dropbox.files.FileMetadata`` and
``FolderMetadata`` objects drive the isinstance-based filtering.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_processor.sources.base import SourceFile


def _file_meta(name, file_id, size, path_display, modified=datetime(2025, 1, 1)):
    import dropbox

    return dropbox.files.FileMetadata(
        name=name,
        id=file_id,
        size=size,
        server_modified=modified,
        path_display=path_display,
    )


class TestDropboxAuthToken:
    def test_authenticate_with_access_token(self):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource(access_token="tok")
        mock_dbx = MagicMock()
        with patch("dropbox.Dropbox", return_value=mock_dbx):
            assert source.authenticate() is True
        assert source.dbx is mock_dbx
        mock_dbx.users_get_current_account.assert_called_once()

    def test_authenticate_access_token_failure(self):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource(access_token="bad")
        mock_dbx = MagicMock()
        mock_dbx.users_get_current_account.side_effect = Exception("401 unauthorized")
        with patch("dropbox.Dropbox", return_value=mock_dbx):
            assert source.authenticate() is False


class TestDropboxAuthSavedToken:
    @patch.dict(os.environ, {}, clear=True)
    def test_authenticate_saved_token(self, tmp_path):
        from video_processor.sources.dropbox_source import DropboxSource

        token_file = tmp_path / "token.json"
        token_file.write_text(
            json.dumps({"refresh_token": "rt", "app_key": "k", "app_secret": "s"})
        )
        source = DropboxSource(token_path=token_file)
        mock_dbx = MagicMock()
        with patch("dropbox.Dropbox", return_value=mock_dbx):
            assert source.authenticate() is True
        assert source.dbx is mock_dbx

    @patch.dict(os.environ, {}, clear=True)
    def test_authenticate_saved_token_invalid_falls_through(self, tmp_path):
        from video_processor.sources.dropbox_source import DropboxSource

        # Missing refresh_token => _auth_saved_token returns False, then OAuth is
        # attempted, which fails because no app_key is configured.
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"app_key": "k"}))
        source = DropboxSource(token_path=token_file)
        assert source.authenticate() is False

    def test_auth_saved_token_corrupt_json(self, tmp_path):
        import dropbox

        from video_processor.sources.dropbox_source import DropboxSource

        token_file = tmp_path / "token.json"
        token_file.write_text("{not valid json")
        source = DropboxSource(token_path=token_file, app_key="k", app_secret="s")
        assert source._auth_saved_token(dropbox) is False


class TestDropboxAuthOAuth:
    @patch.dict(os.environ, {}, clear=True)
    def test_authenticate_oauth_no_app_key(self, tmp_path):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource(token_path=tmp_path / "missing.json")
        # No access token, no saved token, no app_key => OAuth bails out.
        assert source.authenticate() is False

    def test_auth_oauth_full_flow(self, tmp_path):
        import dropbox

        from video_processor.sources.dropbox_source import DropboxSource

        token_file = tmp_path / "sub" / "token.json"
        source = DropboxSource(app_key="appkey", app_secret="appsecret", token_path=token_file)

        flow = MagicMock()
        flow.start.return_value = "https://dropbox.com/authorize?x=1"
        result = MagicMock()
        result.refresh_token = "new_refresh"
        flow.finish.return_value = result
        mock_dbx = MagicMock()

        # webbrowser.open raising (e.g. headless host) must be swallowed so the
        # flow still completes via the printed URL + pasted code.
        with (
            patch("dropbox.DropboxOAuth2FlowNoRedirect", return_value=flow),
            patch("dropbox.Dropbox", return_value=mock_dbx),
            patch("builtins.input", return_value="authcode123"),
            patch(
                "video_processor.sources.dropbox_source.webbrowser.open",
                side_effect=Exception("no display"),
            ),
        ):
            assert source._auth_oauth(dropbox) is True

        assert source.dbx is mock_dbx
        flow.finish.assert_called_once_with("authcode123")
        assert token_file.exists()
        saved = json.loads(token_file.read_text())
        assert saved["refresh_token"] == "new_refresh"
        assert saved["app_key"] == "appkey"
        assert saved["app_secret"] == "appsecret"

    def test_auth_oauth_exception(self):
        import dropbox

        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource(app_key="appkey")
        with patch("dropbox.DropboxOAuth2FlowNoRedirect", side_effect=Exception("boom")):
            assert source._auth_oauth(dropbox) is False


class TestDropboxListVideos:
    def test_list_videos_filters_and_normalizes_path(self):
        import dropbox

        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource()
        source.dbx = MagicMock()

        entries = [
            _file_meta("clip.mp4", "id:1", 1000, "/recordings/clip.mp4"),
            _file_meta("notes.txt", "id:2", 50, "/recordings/notes.txt"),
            dropbox.files.FolderMetadata(name="sub", id="id:3"),
        ]
        result = MagicMock()
        result.entries = entries
        result.has_more = False
        source.dbx.files_list_folder.return_value = result

        files = source.list_videos(folder_path="recordings")

        # Only the video FileMetadata survives ext + isinstance filtering.
        assert len(files) == 1
        sf = files[0]
        assert sf.name == "clip.mp4"
        assert sf.id == "id:1"
        assert sf.size_bytes == 1000
        assert sf.path == "/recordings/clip.mp4"
        assert sf.modified_at == "2025-01-01T00:00:00"
        assert sf.mime_type is None
        # A leading slash is added to a bare folder path.
        source.dbx.files_list_folder.assert_called_once_with("/recordings", recursive=False)

    def test_list_videos_pagination(self):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource()
        source.dbx = MagicMock()

        page1 = MagicMock()
        page1.entries = [_file_meta("a.mov", "id:a", 10, "/a.mov")]
        page1.has_more = True
        page1.cursor = "cursor1"

        page2 = MagicMock()
        page2.entries = [_file_meta("b.mkv", "id:b", 20, "/b.mkv")]
        page2.has_more = False

        source.dbx.files_list_folder.return_value = page1
        source.dbx.files_list_folder_continue.return_value = page2

        files = source.list_videos()

        assert {f.name for f in files} == {"a.mov", "b.mkv"}
        # Empty folder path stays "" (no leading slash added).
        source.dbx.files_list_folder.assert_called_once_with("", recursive=False)
        source.dbx.files_list_folder_continue.assert_called_once_with("cursor1")

    def test_list_videos_pattern_filter(self):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource()
        source.dbx = MagicMock()

        entries = [
            _file_meta("clip.mp4", "id:1", 1, "/clip.mp4"),
            _file_meta("movie.mov", "id:2", 1, "/movie.mov"),
        ]
        result = MagicMock()
        result.entries = entries
        result.has_more = False
        source.dbx.files_list_folder.return_value = result

        files = source.list_videos(patterns=["*.mp4"])

        assert len(files) == 1
        assert files[0].name == "clip.mp4"

    def test_list_videos_error_reraises(self):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource()
        source.dbx = MagicMock()
        source.dbx.files_list_folder.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            source.list_videos(folder_path="/recordings")


class TestDropboxDownload:
    def test_download_writes_file(self, tmp_path):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource()
        source.dbx = MagicMock()

        def fake_download(dest, path):
            Path(dest).write_bytes(b"video-bytes")

        source.dbx.files_download_to_file.side_effect = fake_download

        f = SourceFile(name="clip.mp4", id="id:1", path="/recordings/clip.mp4")
        dest = tmp_path / "out" / "clip.mp4"
        result = source.download(f, dest)

        assert result == dest
        assert dest.read_bytes() == b"video-bytes"
        source.dbx.files_download_to_file.assert_called_once_with(str(dest), "/recordings/clip.mp4")

    def test_download_path_fallback_to_name(self, tmp_path):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource()
        source.dbx = MagicMock()

        def fake_download(dest, path):
            Path(dest).write_text("data")

        source.dbx.files_download_to_file.side_effect = fake_download

        f = SourceFile(name="video.mp4", id="id:1")  # no path
        dest = tmp_path / "video.mp4"
        source.download(f, dest)

        # Falls back to "/{name}" when SourceFile.path is None.
        source.dbx.files_download_to_file.assert_called_once_with(str(dest), "/video.mp4")
