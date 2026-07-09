"""Tests for the Zoom cloud recordings source (video_processor.sources.zoom_source).

Mocks are applied only at the ``requests`` boundary (plus ``webbrowser``/``input``
for the interactive PKCE flow). Real token files are written to ``tmp_path`` and
read back to assert on persisted contents.
"""

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from video_processor.sources.base import SourceFile
from video_processor.sources.zoom_source import ZoomSource


def _mock_response(*, json_data=None, text=None, chunks=None, raise_error=None):
    """Build a MagicMock that mimics the parts of requests.Response we use."""
    resp = MagicMock()
    if raise_error is None:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = raise_error
    if json_data is not None:
        resp.json.return_value = json_data
    if text is not None:
        resp.text = text
    if chunks is not None:
        resp.iter_content.return_value = chunks
    return resp


class TestZoomSavedToken:
    def test_valid_token_sets_access_token(self, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        token_file.write_text(
            json.dumps({"access_token": "valid-token", "expires_at": time.time() + 10_000})
        )
        src = ZoomSource(token_path=token_file)
        assert src._auth_saved_token() is True
        assert src._access_token == "valid-token"
        assert src._token_data["access_token"] == "valid-token"

    def test_expired_with_refresh_token_delegates_to_refresh(self, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        token_file.write_text(
            json.dumps({"access_token": "old", "expires_at": 0, "refresh_token": "rt"})
        )
        src = ZoomSource(token_path=token_file)
        with patch.object(src, "_refresh_token", return_value=True) as mock_refresh:
            assert src._auth_saved_token() is True
            mock_refresh.assert_called_once()

    def test_expired_without_refresh_token_returns_false(self, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        token_file.write_text(json.dumps({"access_token": "old", "expires_at": 0}))
        src = ZoomSource(token_path=token_file)
        assert src._auth_saved_token() is False
        assert src._access_token is None

    def test_missing_file_returns_false(self, tmp_path):
        src = ZoomSource(token_path=tmp_path / "does-not-exist.json")
        assert src._auth_saved_token() is False

    def test_malformed_json_returns_false(self, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        token_file.write_text("not valid json {{{")
        src = ZoomSource(token_path=token_file)
        assert src._auth_saved_token() is False


class TestZoomServerToServer:
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_credentials_returns_false(self):
        src = ZoomSource(client_id=None, client_secret=None, account_id="acct")
        assert src._auth_server_to_server() is False

    @patch("video_processor.sources.zoom_source.requests.post")
    def test_success_persists_token(self, mock_post, tmp_path):
        token_file = tmp_path / ".planopticon" / "zoom_token.json"
        mock_post.return_value = _mock_response(
            json_data={
                "access_token": "s2s-token",
                "expires_in": 3600,
                "token_type": "bearer",
            }
        )
        src = ZoomSource(
            client_id="cid",
            client_secret="sec",
            account_id="acct",
            token_path=token_file,
        )
        assert src._auth_server_to_server() is True
        assert src._access_token == "s2s-token"
        saved = json.loads(token_file.read_text())
        assert saved["access_token"] == "s2s-token"
        assert "refresh_token" not in saved
        _, kwargs = mock_post.call_args
        assert kwargs["auth"] == ("cid", "sec")
        assert kwargs["params"]["grant_type"] == "account_credentials"
        assert kwargs["params"]["account_id"] == "acct"

    @patch("video_processor.sources.zoom_source.requests.post")
    def test_http_error_returns_false(self, mock_post, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        mock_post.return_value = _mock_response(raise_error=requests.HTTPError("500"))
        src = ZoomSource(
            client_id="cid",
            client_secret="sec",
            account_id="acct",
            token_path=token_file,
        )
        assert src._auth_server_to_server() is False
        assert src._access_token is None
        assert not token_file.exists()


class TestZoomOAuthPKCE:
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_client_id_returns_false(self):
        src = ZoomSource(client_id=None)
        assert src._auth_oauth_pkce() is False

    @patch("video_processor.sources.zoom_source.requests.post")
    @patch("builtins.input", return_value="the-auth-code")
    @patch("video_processor.sources.zoom_source.webbrowser.open")
    def test_success_persists_token(self, mock_open, mock_input, mock_post, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        mock_post.return_value = _mock_response(
            json_data={
                "access_token": "pkce-token",
                "refresh_token": "pkce-refresh",
                "expires_in": 3600,
                "token_type": "bearer",
            }
        )
        src = ZoomSource(client_id="cid", client_secret="csec", token_path=token_file)
        assert src._auth_oauth_pkce() is True
        assert src._access_token == "pkce-token"
        mock_open.assert_called_once()
        mock_input.assert_called_once()
        saved = json.loads(token_file.read_text())
        assert saved["access_token"] == "pkce-token"
        assert saved["refresh_token"] == "pkce-refresh"
        assert saved["client_id"] == "cid"
        _, kwargs = mock_post.call_args
        assert kwargs["data"]["grant_type"] == "authorization_code"
        assert kwargs["data"]["code"] == "the-auth-code"

    @patch("video_processor.sources.zoom_source.requests.post")
    @patch("builtins.input", return_value="code2")
    @patch(
        "video_processor.sources.zoom_source.webbrowser.open",
        side_effect=Exception("no browser available"),
    )
    def test_browser_open_failure_is_ignored(self, mock_open, mock_input, mock_post, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        mock_post.return_value = _mock_response(
            json_data={"access_token": "tok", "expires_in": 3600}
        )
        src = ZoomSource(client_id="cid", token_path=token_file)
        assert src._auth_oauth_pkce() is True
        assert src._access_token == "tok"
        mock_input.assert_called_once()

    @patch("video_processor.sources.zoom_source.requests.post")
    @patch("builtins.input", return_value="the-auth-code")
    @patch("video_processor.sources.zoom_source.webbrowser.open")
    def test_token_exchange_error_returns_false(self, mock_open, mock_input, mock_post, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        mock_post.return_value = _mock_response(raise_error=requests.HTTPError("bad code"))
        src = ZoomSource(client_id="cid", client_secret="csec", token_path=token_file)
        assert src._auth_oauth_pkce() is False
        assert src._access_token is None
        assert not token_file.exists()


class TestZoomRefreshToken:
    @patch("video_processor.sources.zoom_source.requests.post")
    def test_success_rewrites_token(self, mock_post, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        token_file.write_text(
            json.dumps(
                {
                    "access_token": "old",
                    "refresh_token": "old-refresh",
                    "client_id": "cid",
                    "client_secret": "sec",
                    "expires_at": 0,
                }
            )
        )
        mock_post.return_value = _mock_response(
            json_data={
                "access_token": "refreshed",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
            }
        )
        src = ZoomSource(token_path=token_file)
        assert src._refresh_token() is True
        assert src._access_token == "refreshed"
        saved = json.loads(token_file.read_text())
        assert saved["access_token"] == "refreshed"
        assert saved["refresh_token"] == "new-refresh"
        _, kwargs = mock_post.call_args
        assert kwargs["data"]["grant_type"] == "refresh_token"
        assert kwargs["auth"] == ("cid", "sec")

    @patch("video_processor.sources.zoom_source.requests.post")
    def test_keeps_old_refresh_token_when_response_omits_it(self, mock_post, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        token_file.write_text(
            json.dumps({"refresh_token": "old-refresh", "client_id": "cid", "client_secret": "sec"})
        )
        mock_post.return_value = _mock_response(
            json_data={"access_token": "refreshed", "expires_in": 3600}
        )
        src = ZoomSource(token_path=token_file)
        assert src._refresh_token() is True
        saved = json.loads(token_file.read_text())
        assert saved["refresh_token"] == "old-refresh"

    def test_missing_refresh_token_returns_false(self, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        token_file.write_text(json.dumps({"client_id": "cid"}))
        src = ZoomSource(token_path=token_file)
        assert src._refresh_token() is False

    @patch("video_processor.sources.zoom_source.requests.post")
    def test_http_error_returns_false(self, mock_post, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        token_file.write_text(
            json.dumps({"refresh_token": "rt", "client_id": "cid", "client_secret": "sec"})
        )
        mock_post.return_value = _mock_response(raise_error=requests.HTTPError("bad"))
        src = ZoomSource(token_path=token_file)
        assert src._refresh_token() is False


class TestZoomAuthenticateDispatch:
    def test_saved_token_path(self, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        token_file.write_text(json.dumps({"access_token": "x", "expires_at": 0}))
        src = ZoomSource(token_path=token_file)
        with patch.object(src, "_auth_saved_token", return_value=True) as mock_saved:
            assert src.authenticate() is True
            mock_saved.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    def test_account_id_path(self, tmp_path):
        src = ZoomSource(account_id="acct", token_path=tmp_path / "none.json")
        with patch.object(src, "_auth_server_to_server", return_value=True) as mock_s2s:
            assert src.authenticate() is True
            mock_s2s.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    def test_pkce_path(self, tmp_path):
        src = ZoomSource(token_path=tmp_path / "none.json")
        with patch.object(src, "_auth_oauth_pkce", return_value=True) as mock_pkce:
            assert src.authenticate() is True
            mock_pkce.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    def test_saved_token_failure_falls_back_to_account(self, tmp_path):
        token_file = tmp_path / "zoom_token.json"
        token_file.write_text(json.dumps({"access_token": "x", "expires_at": 0}))
        src = ZoomSource(account_id="acct", token_path=token_file)
        with (
            patch.object(src, "_auth_saved_token", return_value=False),
            patch.object(src, "_auth_server_to_server", return_value=True) as mock_s2s,
        ):
            assert src.authenticate() is True
            mock_s2s.assert_called_once()


class TestZoomApiGet:
    def test_not_authenticated_raises(self):
        src = ZoomSource()
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src._api_get("users/me/recordings")

    @patch("video_processor.sources.zoom_source.requests.get")
    def test_authenticated_returns_response(self, mock_get):
        resp = _mock_response(json_data={"ok": True})
        mock_get.return_value = resp
        src = ZoomSource()
        src._access_token = "tok"
        result = src._api_get("/users/me/recordings", params={"a": "b"})
        assert result is resp
        url = mock_get.call_args.args[0]
        assert url.endswith("/users/me/recordings")
        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer tok"
        assert kwargs["params"] == {"a": "b"}


class TestZoomListVideos:
    def test_not_authenticated_raises(self):
        src = ZoomSource()
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src.list_videos()

    @patch("video_processor.sources.zoom_source.requests.get")
    def test_pagination_and_parsing(self, mock_get):
        page1 = _mock_response(
            json_data={
                "meetings": [
                    {
                        "id": 111,
                        "topic": "Standup",
                        "start_time": "2026-01-01T00:00:00Z",
                        "recording_files": [
                            {
                                "file_type": "MP4",
                                "file_extension": "MP4",
                                "file_size": 1000,
                                "download_url": "https://dl/1",
                            },
                            {
                                "file_type": "M4A",
                                "file_extension": "M4A",
                                "file_size": 500,
                                "download_url": "https://dl/2",
                            },
                        ],
                    }
                ],
                "next_page_token": "PAGE2",
            }
        )
        page2 = _mock_response(
            json_data={
                "meetings": [
                    {
                        "id": 222,
                        "topic": "Retro",
                        "recording_files": [
                            {
                                "file_type": "TRANSCRIPT",
                                "file_extension": "VTT",
                                "download_url": "https://dl/3",
                            }
                        ],
                    }
                ],
                "next_page_token": "",
            }
        )
        mock_get.side_effect = [page1, page2]
        src = ZoomSource()
        src._access_token = "tok"
        files = src.list_videos()
        assert mock_get.call_count == 2
        assert [f.name for f in files] == ["Standup.mp4", "Standup.m4a", "Retro.vtt"]
        assert [f.mime_type for f in files] == ["video/mp4", "audio/mp4", "text/vtt"]
        assert [f.path for f in files] == ["https://dl/1", "https://dl/2", "https://dl/3"]
        assert [f.id for f in files] == ["111", "111", "222"]
        assert mock_get.call_args_list[1].kwargs["params"]["next_page_token"] == "PAGE2"

    @patch("video_processor.sources.zoom_source.requests.get")
    def test_pattern_filter_excludes_non_matching(self, mock_get):
        mock_get.return_value = _mock_response(
            json_data={
                "meetings": [
                    {
                        "id": 5,
                        "topic": "Sync",
                        "recording_files": [
                            {
                                "file_type": "MP4",
                                "file_extension": "mp4",
                                "download_url": "https://dl/a",
                            },
                            {
                                "file_type": "TRANSCRIPT",
                                "file_extension": "vtt",
                                "download_url": "https://dl/b",
                            },
                        ],
                    }
                ],
                "next_page_token": "",
            }
        )
        src = ZoomSource()
        src._access_token = "tok"
        files = src.list_videos(patterns=["*.mp4"])
        assert len(files) == 1
        assert files[0].name == "Sync.mp4"


class TestZoomDownload:
    def test_not_authenticated_raises(self, tmp_path):
        src = ZoomSource()
        f = SourceFile(name="x.mp4", id="1", path="https://dl/x")
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src.download(f, tmp_path / "x.mp4")

    def test_missing_download_url_raises_value_error(self, tmp_path):
        src = ZoomSource()
        src._access_token = "tok"
        f = SourceFile(name="x.mp4", id="1")
        with pytest.raises(ValueError, match="No download URL"):
            src.download(f, tmp_path / "x.mp4")

    @patch("video_processor.sources.zoom_source.requests.get")
    def test_success_streams_chunks_to_file(self, mock_get, tmp_path):
        mock_get.return_value = _mock_response(chunks=[b"aaa", b"bbb"])
        src = ZoomSource()
        src._access_token = "tok"
        f = SourceFile(name="x.mp4", id="1", path="https://dl/x")
        dest = tmp_path / "sub" / "x.mp4"
        result = src.download(f, dest)
        assert result == dest
        assert dest.read_bytes() == b"aaabbb"
        _, kwargs = mock_get.call_args
        assert kwargs["stream"] is True
        assert kwargs["headers"]["Authorization"] == "Bearer tok"


class TestZoomFetchTranscript:
    def test_not_authenticated_raises(self):
        src = ZoomSource()
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src.fetch_transcript("m1")

    @patch("video_processor.sources.zoom_source.requests.get")
    def test_transcript_present_returns_text(self, mock_get):
        api_resp = _mock_response(
            json_data={
                "recording_files": [{"file_type": "TRANSCRIPT", "download_url": "https://t"}]
            }
        )
        dl_resp = _mock_response(text="WEBVTT\nhello")
        mock_get.side_effect = [api_resp, dl_resp]
        src = ZoomSource()
        src._access_token = "tok"
        assert src.fetch_transcript("m1") == "WEBVTT\nhello"
        assert mock_get.call_count == 2

    @patch("video_processor.sources.zoom_source.requests.get")
    def test_transcript_present_without_url_returns_none(self, mock_get):
        mock_get.return_value = _mock_response(
            json_data={"recording_files": [{"file_type": "TRANSCRIPT"}]}
        )
        src = ZoomSource()
        src._access_token = "tok"
        assert src.fetch_transcript("m1") is None
        assert mock_get.call_count == 1

    @patch("video_processor.sources.zoom_source.requests.get")
    def test_no_transcript_returns_none(self, mock_get):
        mock_get.return_value = _mock_response(
            json_data={"recording_files": [{"file_type": "MP4", "download_url": "x"}]}
        )
        src = ZoomSource()
        src._access_token = "tok"
        assert src.fetch_transcript("m1") is None

    @patch("video_processor.sources.zoom_source.requests.get")
    def test_exception_returns_none(self, mock_get):
        mock_get.side_effect = requests.RequestException("boom")
        src = ZoomSource()
        src._access_token = "tok"
        assert src.fetch_transcript("m1") is None
