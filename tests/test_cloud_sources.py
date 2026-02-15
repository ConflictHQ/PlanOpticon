"""Tests for cloud source integrations."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_processor.sources.base import BaseSource, SourceFile


class TestSourceFile:
    def test_basic(self):
        f = SourceFile(name="video.mp4", id="abc123")
        assert f.name == "video.mp4"
        assert f.id == "abc123"

    def test_full(self):
        f = SourceFile(
            name="meeting.mp4",
            id="xyz",
            size_bytes=1024000,
            mime_type="video/mp4",
            modified_at="2025-01-01T00:00:00Z",
            path="/recordings/meeting.mp4",
        )
        assert f.size_bytes == 1024000
        assert f.path == "/recordings/meeting.mp4"

    def test_round_trip(self):
        f = SourceFile(name="test.mp4", id="1")
        data = f.model_dump_json()
        restored = SourceFile.model_validate_json(data)
        assert restored.name == f.name


class TestBaseSource:
    def test_download_all(self, tmp_path):
        class FakeSource(BaseSource):
            def authenticate(self):
                return True

            def list_videos(self, **kwargs):
                return []

            def download(self, file, destination):
                destination.write_text("fake video data")
                return destination

        source = FakeSource()
        files = [
            SourceFile(name="a.mp4", id="1"),
            SourceFile(name="b.mp4", id="2"),
        ]
        paths = source.download_all(files, tmp_path / "downloads")
        assert len(paths) == 2
        assert (tmp_path / "downloads" / "a.mp4").exists()
        assert (tmp_path / "downloads" / "b.mp4").exists()

    def test_download_all_handles_errors(self, tmp_path):
        class FailingSource(BaseSource):
            def authenticate(self):
                return True

            def list_videos(self, **kwargs):
                return []

            def download(self, file, destination):
                raise RuntimeError("Download failed")

        source = FailingSource()
        files = [SourceFile(name="fail.mp4", id="1")]
        paths = source.download_all(files, tmp_path / "downloads")
        assert len(paths) == 0


class TestGoogleDriveSource:
    def test_init_defaults(self):
        from video_processor.sources.google_drive import GoogleDriveSource

        source = GoogleDriveSource()
        assert source.service is None
        assert source.use_service_account is None

    def test_init_with_credentials(self):
        from video_processor.sources.google_drive import GoogleDriveSource

        source = GoogleDriveSource(
            credentials_path="/path/to/creds.json",
            use_service_account=True,
        )
        assert source.credentials_path == "/path/to/creds.json"
        assert source.use_service_account is True

    def test_is_service_account_true(self, tmp_path):
        from video_processor.sources.google_drive import GoogleDriveSource

        creds_file = tmp_path / "sa.json"
        creds_file.write_text(json.dumps({"type": "service_account"}))
        source = GoogleDriveSource(credentials_path=str(creds_file))
        assert source._is_service_account() is True

    def test_is_service_account_false(self, tmp_path):
        from video_processor.sources.google_drive import GoogleDriveSource

        creds_file = tmp_path / "oauth.json"
        creds_file.write_text(json.dumps({"installed": {}}))
        source = GoogleDriveSource(credentials_path=str(creds_file))
        assert source._is_service_account() is False

    @patch.dict("os.environ", {}, clear=True)
    def test_is_service_account_no_path(self):
        from video_processor.sources.google_drive import GoogleDriveSource

        source = GoogleDriveSource(credentials_path=None)
        source.credentials_path = None  # Override any env var fallback
        assert source._is_service_account() is False

    def test_list_videos_not_authenticated(self):
        from video_processor.sources.google_drive import GoogleDriveSource

        source = GoogleDriveSource()
        with pytest.raises(RuntimeError, match="Not authenticated"):
            source.list_videos(folder_id="abc")

    def test_download_not_authenticated(self):
        from video_processor.sources.google_drive import GoogleDriveSource

        source = GoogleDriveSource()
        f = SourceFile(name="test.mp4", id="1")
        with pytest.raises(RuntimeError, match="Not authenticated"):
            source.download(f, Path("/tmp/test.mp4"))

    @patch("video_processor.sources.google_drive.GoogleDriveSource._auth_service_account")
    def test_authenticate_import_error(self, mock_auth):
        from video_processor.sources.google_drive import GoogleDriveSource

        source = GoogleDriveSource()
        with patch.dict(
            "sys.modules", {"google.oauth2": None, "google.oauth2.service_account": None}
        ):
            # The import will fail inside authenticate
            result = source.authenticate()
            assert result is False


class TestDropboxSource:
    def test_init_defaults(self):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource()
        assert source.dbx is None

    def test_init_with_token(self):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource(access_token="test_token")
        assert source.access_token == "test_token"

    def test_init_with_app_key(self):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource(app_key="key", app_secret="secret")
        assert source.app_key == "key"
        assert source.app_secret == "secret"

    def test_list_videos_not_authenticated(self):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource()
        with pytest.raises(RuntimeError, match="Not authenticated"):
            source.list_videos(folder_path="/recordings")

    def test_download_not_authenticated(self):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource()
        f = SourceFile(name="test.mp4", id="1", path="/test.mp4")
        with pytest.raises(RuntimeError, match="Not authenticated"):
            source.download(f, Path("/tmp/test.mp4"))

    def test_authenticate_no_sdk(self):
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource()
        with patch.dict("sys.modules", {"dropbox": None}):
            result = source.authenticate()
            assert result is False

    def test_auth_saved_token(self, tmp_path):
        pytest.importorskip("dropbox")
        from video_processor.sources.dropbox_source import DropboxSource

        token_file = tmp_path / "token.json"
        token_file.write_text(
            json.dumps(
                {
                    "refresh_token": "rt_test",
                    "app_key": "key",
                    "app_secret": "secret",
                }
            )
        )

        source = DropboxSource(token_path=token_file, app_key="key", app_secret="secret")

        mock_dbx = MagicMock()
        with patch("dropbox.Dropbox", return_value=mock_dbx):
            import dropbox

            result = source._auth_saved_token(dropbox)
            assert result is True
            assert source.dbx is mock_dbx
