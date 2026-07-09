"""Tests for TwitterSource: auth fallback, fetch, and download.

Complements the import / constructor / authenticate / list_videos cases in
tests/test_sources.py by exercising the gallery-dl auth branch, download,
fetch_text routing, the API path, and the gallery-dl path. Network and
subprocess boundaries are mocked; the real ``requests`` module stays intact so
its exception types propagate through error handling.
"""

import json
import os
import types
from unittest.mock import MagicMock, patch

import pytest

from video_processor.sources.base import SourceFile


class TestTwitterAuthenticate:
    @patch.dict(os.environ, {}, clear=True)
    def test_authenticate_gallery_dl_available(self):
        from video_processor.sources.twitter_source import TwitterSource

        fake_gdl = types.ModuleType("gallery_dl")
        with patch.dict("sys.modules", {"gallery_dl": fake_gdl}):
            src = TwitterSource(url="https://twitter.com/u/status/1")
            assert src.authenticate() is True


class TestTwitterFetchViaApi:
    @patch("requests.get")
    def test_fetch_via_api(self, mock_get):
        from video_processor.sources.twitter_source import TwitterSource

        resp = MagicMock()
        resp.json.return_value = {
            "data": {
                "text": "Hello tweet",
                "created_at": "2026-01-01T00:00:00Z",
                "author_id": "42",
            }
        }
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        src = TwitterSource(url="https://twitter.com/user/status/1234567890")
        src._bearer_token = "test_token"
        text = src.fetch_text()

        assert "Hello tweet" in text
        assert "2026-01-01T00:00:00Z" in text
        args, kwargs = mock_get.call_args
        assert "1234567890" in args[0]
        assert kwargs["headers"]["Authorization"] == "Bearer test_token"

    def test_fetch_via_api_invalid_url(self):
        from video_processor.sources.twitter_source import TwitterSource

        src = TwitterSource(url="https://twitter.com/user/profile")  # no /status/
        src._bearer_token = "token"
        with pytest.raises(ValueError, match="Could not extract tweet ID"):
            src.fetch_text()

    @patch("requests.get")
    def test_fetch_via_api_http_error_propagates(self, mock_get):
        import requests

        from video_processor.sources.twitter_source import TwitterSource

        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.HTTPError("401")
        mock_get.return_value = resp

        src = TwitterSource(url="https://twitter.com/u/status/999")
        src._bearer_token = "bad"
        with pytest.raises(requests.HTTPError):
            src.fetch_text()


class TestTwitterFetchViaGalleryDl:
    @patch("subprocess.run")
    def test_fetch_via_gallery_dl_list(self, mock_run):
        from video_processor.sources.twitter_source import TwitterSource

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([{"content": "First tweet"}, {"text": "Second tweet"}]),
            stderr="",
        )
        src = TwitterSource(url="https://twitter.com/u/status/1")  # no bearer token
        text = src.fetch_text()

        assert "First tweet" in text
        assert "Second tweet" in text

    @patch("subprocess.run")
    def test_fetch_via_gallery_dl_single_dict(self, mock_run):
        from video_processor.sources.twitter_source import TwitterSource

        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({"content": "Only tweet"}), stderr=""
        )
        src = TwitterSource(url="https://twitter.com/u/status/1")
        assert src.fetch_text() == "Only tweet"

    @patch("subprocess.run")
    def test_fetch_via_gallery_dl_failure(self, mock_run):
        from video_processor.sources.twitter_source import TwitterSource

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="gallery-dl error")
        src = TwitterSource(url="https://twitter.com/u/status/1")
        with pytest.raises(RuntimeError, match="gallery-dl failed"):
            src.fetch_text()

    @patch("subprocess.run")
    def test_fetch_via_gallery_dl_no_text(self, mock_run):
        from video_processor.sources.twitter_source import TwitterSource

        # Non-dict items are skipped, leaving no extractable text.
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps([["not", "a", "dict"], 42]), stderr=""
        )
        src = TwitterSource(url="https://twitter.com/u/status/1")
        assert src.fetch_text() == "No text content extracted."

    def test_fetch_text_no_method_raises(self):
        from video_processor.sources.twitter_source import TwitterSource

        src = TwitterSource(url="https://twitter.com/u/status/1")
        with patch.object(
            TwitterSource, "_fetch_via_gallery_dl", side_effect=ImportError("no gdl")
        ):
            with pytest.raises(RuntimeError, match="No Twitter extraction method"):
                src.fetch_text()


class TestTwitterDownload:
    @patch("requests.get")
    def test_download_writes_file(self, mock_get, tmp_path):
        from video_processor.sources.twitter_source import TwitterSource

        resp = MagicMock()
        resp.json.return_value = {"data": {"text": "Downloaded tweet", "created_at": "2026-02-02"}}
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        src = TwitterSource(url="https://twitter.com/u/status/555")
        src._bearer_token = "token"
        dest = tmp_path / "out" / "tweet.txt"

        result = src.download(SourceFile(name="tweet", id="x"), dest)

        assert result == dest
        content = dest.read_text()
        assert "Downloaded tweet" in content
        assert "2026-02-02" in content
