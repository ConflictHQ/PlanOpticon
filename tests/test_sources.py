"""Tests for all source connectors: import, instantiation, authenticate, list_videos."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_processor.sources.base import BaseSource, SourceFile

# ---------------------------------------------------------------------------
# SourceFile model
# ---------------------------------------------------------------------------


def test_source_file_creation():
    sf = SourceFile(name="test.mp4", id="abc123")
    assert sf.name == "test.mp4"
    assert sf.id == "abc123"
    assert sf.size_bytes is None
    assert sf.mime_type is None


def test_source_file_with_all_fields():
    sf = SourceFile(
        name="video.mp4",
        id="v1",
        size_bytes=1024,
        mime_type="video/mp4",
        modified_at="2025-01-01",
        path="folder/video.mp4",
    )
    assert sf.size_bytes == 1024
    assert sf.path == "folder/video.mp4"


# ---------------------------------------------------------------------------
# YouTubeSource
# ---------------------------------------------------------------------------


class TestYouTubeSource:
    def test_import(self):
        from video_processor.sources.youtube_source import YouTubeSource

        assert YouTubeSource is not None

    def test_constructor(self):
        from video_processor.sources.youtube_source import YouTubeSource

        src = YouTubeSource(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert src.video_id == "dQw4w9WgXcQ"
        assert src.audio_only is False

    def test_constructor_audio_only(self):
        from video_processor.sources.youtube_source import YouTubeSource

        src = YouTubeSource(url="https://youtu.be/dQw4w9WgXcQ", audio_only=True)
        assert src.audio_only is True

    def test_constructor_shorts_url(self):
        from video_processor.sources.youtube_source import YouTubeSource

        src = YouTubeSource(url="https://youtube.com/shorts/dQw4w9WgXcQ")
        assert src.video_id == "dQw4w9WgXcQ"

    def test_constructor_invalid_url(self):
        from video_processor.sources.youtube_source import YouTubeSource

        with pytest.raises(ValueError, match="Could not extract"):
            YouTubeSource(url="https://example.com/not-youtube")

    @patch.dict(os.environ, {}, clear=False)
    def test_authenticate_no_ytdlp(self):
        from video_processor.sources.youtube_source import YouTubeSource

        src = YouTubeSource(url="https://youtube.com/watch?v=dQw4w9WgXcQ")
        with patch.dict("sys.modules", {"yt_dlp": None}):
            # yt_dlp import will fail
            result = src.authenticate()
            # Result depends on whether yt_dlp is installed; just check it returns bool
            assert isinstance(result, bool)

    def test_list_videos(self):
        from video_processor.sources.youtube_source import YouTubeSource

        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "title": "Test Video",
            "filesize": 1000,
        }
        mock_ydl_cls = MagicMock(return_value=mock_ydl)
        mock_module = MagicMock()
        mock_module.YoutubeDL = mock_ydl_cls

        with patch.dict("sys.modules", {"yt_dlp": mock_module}):
            src = YouTubeSource(url="https://youtube.com/watch?v=dQw4w9WgXcQ")
            files = src.list_videos()
            assert isinstance(files, list)
            assert len(files) == 1
            assert files[0].name == "Test Video"


# ---------------------------------------------------------------------------
# WebSource
# ---------------------------------------------------------------------------


class TestWebSource:
    def test_import(self):
        from video_processor.sources.web_source import WebSource

        assert WebSource is not None

    def test_constructor(self):
        from video_processor.sources.web_source import WebSource

        src = WebSource(url="https://example.com/page")
        assert src.url == "https://example.com/page"

    def test_authenticate(self):
        from video_processor.sources.web_source import WebSource

        src = WebSource(url="https://example.com")
        assert src.authenticate() is True

    def test_list_videos(self):
        from video_processor.sources.web_source import WebSource

        src = WebSource(url="https://example.com/article")
        files = src.list_videos()
        assert isinstance(files, list)
        assert len(files) == 1
        assert files[0].mime_type == "text/html"


# ---------------------------------------------------------------------------
# GitHubSource
# ---------------------------------------------------------------------------


class TestGitHubSource:
    def test_import(self):
        from video_processor.sources.github_source import GitHubSource

        assert GitHubSource is not None

    def test_constructor(self):
        from video_processor.sources.github_source import GitHubSource

        src = GitHubSource(repo="owner/repo")
        assert src.repo == "owner/repo"
        assert src.include_issues is True
        assert src.include_prs is True

    @patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test123"})
    def test_authenticate_with_env_token(self):
        from video_processor.sources.github_source import GitHubSource

        src = GitHubSource(repo="owner/repo")
        result = src.authenticate()
        assert result is True
        assert src._token == "ghp_test123"

    @patch("requests.get")
    @patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test123"})
    def test_list_videos(self, mock_get):
        from video_processor.sources.github_source import GitHubSource

        # Mock responses for readme, issues, and PRs
        readme_resp = MagicMock()
        readme_resp.ok = True

        issues_resp = MagicMock()
        issues_resp.ok = True
        issues_resp.json.return_value = [
            {"number": 1, "title": "Bug report", "id": 1},
            {"number": 2, "title": "Feature request", "id": 2, "pull_request": {}},
        ]

        prs_resp = MagicMock()
        prs_resp.ok = True
        prs_resp.json.return_value = [
            {"number": 3, "title": "Fix bug"},
        ]

        mock_get.side_effect = [readme_resp, issues_resp, prs_resp]

        src = GitHubSource(repo="owner/repo")
        src.authenticate()
        files = src.list_videos()
        assert isinstance(files, list)
        # README + 1 issue (one filtered as PR) + 1 PR = 3
        assert len(files) == 3


# ---------------------------------------------------------------------------
# RedditSource
# ---------------------------------------------------------------------------


class TestRedditSource:
    def test_import(self):
        from video_processor.sources.reddit_source import RedditSource

        assert RedditSource is not None

    def test_constructor(self):
        from video_processor.sources.reddit_source import RedditSource

        src = RedditSource(url="https://reddit.com/r/python/comments/abc123/test/")
        assert src.url == "https://reddit.com/r/python/comments/abc123/test"

    def test_authenticate(self):
        from video_processor.sources.reddit_source import RedditSource

        src = RedditSource(url="https://reddit.com/r/test")
        assert src.authenticate() is True

    def test_list_videos(self):
        from video_processor.sources.reddit_source import RedditSource

        src = RedditSource(url="https://reddit.com/r/python/comments/abc/post")
        files = src.list_videos()
        assert isinstance(files, list)
        assert len(files) == 1
        assert files[0].mime_type == "text/plain"


# ---------------------------------------------------------------------------
# HackerNewsSource
# ---------------------------------------------------------------------------


class TestHackerNewsSource:
    def test_import(self):
        from video_processor.sources.hackernews_source import HackerNewsSource

        assert HackerNewsSource is not None

    def test_constructor(self):
        from video_processor.sources.hackernews_source import HackerNewsSource

        src = HackerNewsSource(item_id=12345678)
        assert src.item_id == 12345678
        assert src.max_comments == 200

    def test_authenticate(self):
        from video_processor.sources.hackernews_source import HackerNewsSource

        src = HackerNewsSource(item_id=12345678)
        assert src.authenticate() is True

    def test_list_videos(self):
        from video_processor.sources.hackernews_source import HackerNewsSource

        src = HackerNewsSource(item_id=99999)
        files = src.list_videos()
        assert isinstance(files, list)
        assert len(files) == 1
        assert files[0].id == "99999"


# ---------------------------------------------------------------------------
# RSSSource
# ---------------------------------------------------------------------------


class TestRSSSource:
    def test_import(self):
        from video_processor.sources.rss_source import RSSSource

        assert RSSSource is not None

    def test_constructor(self):
        from video_processor.sources.rss_source import RSSSource

        src = RSSSource(url="https://example.com/feed.xml", max_entries=20)
        assert src.url == "https://example.com/feed.xml"
        assert src.max_entries == 20

    def test_authenticate(self):
        from video_processor.sources.rss_source import RSSSource

        src = RSSSource(url="https://example.com/feed.xml")
        assert src.authenticate() is True

    @patch("requests.get")
    def test_list_videos(self, mock_get):
        from video_processor.sources.rss_source import RSSSource

        rss_xml = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Entry 1</title>
              <link>https://example.com/1</link>
              <description>First entry</description>
              <pubDate>Mon, 01 Jan 2025 00:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>"""
        mock_resp = MagicMock()
        mock_resp.text = rss_xml
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        src = RSSSource(url="https://example.com/feed.xml")
        files = src.list_videos()
        assert isinstance(files, list)
        assert len(files) >= 1


# ---------------------------------------------------------------------------
# PodcastSource
# ---------------------------------------------------------------------------


class TestPodcastSource:
    def test_import(self):
        from video_processor.sources.podcast_source import PodcastSource

        assert PodcastSource is not None

    def test_constructor(self):
        from video_processor.sources.podcast_source import PodcastSource

        src = PodcastSource(feed_url="https://example.com/podcast.xml", max_episodes=5)
        assert src.feed_url == "https://example.com/podcast.xml"
        assert src.max_episodes == 5

    def test_authenticate(self):
        from video_processor.sources.podcast_source import PodcastSource

        src = PodcastSource(feed_url="https://example.com/podcast.xml")
        assert src.authenticate() is True

    @patch("requests.get")
    def test_list_videos(self, mock_get):
        from video_processor.sources.podcast_source import PodcastSource

        podcast_xml = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Episode 1</title>
              <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" />
              <pubDate>Mon, 01 Jan 2025 00:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>"""
        mock_resp = MagicMock()
        mock_resp.text = podcast_xml
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        src = PodcastSource(feed_url="https://example.com/podcast.xml")
        files = src.list_videos()
        assert isinstance(files, list)
        assert len(files) == 1
        assert files[0].mime_type == "audio/mpeg"


# ---------------------------------------------------------------------------
# TwitterSource
# ---------------------------------------------------------------------------


class TestTwitterSource:
    def test_import(self):
        from video_processor.sources.twitter_source import TwitterSource

        assert TwitterSource is not None

    def test_constructor(self):
        from video_processor.sources.twitter_source import TwitterSource

        src = TwitterSource(url="https://twitter.com/user/status/123456")
        assert src.url == "https://twitter.com/user/status/123456"

    @patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": "test_token"})
    def test_authenticate_with_bearer_token(self):
        from video_processor.sources.twitter_source import TwitterSource

        src = TwitterSource(url="https://twitter.com/user/status/123456")
        assert src.authenticate() is True

    @patch.dict(os.environ, {}, clear=True)
    def test_authenticate_no_token_no_gallery_dl(self):
        from video_processor.sources.twitter_source import TwitterSource

        src = TwitterSource(url="https://twitter.com/user/status/123456")
        with patch.dict("sys.modules", {"gallery_dl": None}):
            result = src.authenticate()
            assert isinstance(result, bool)

    def test_list_videos(self):
        from video_processor.sources.twitter_source import TwitterSource

        src = TwitterSource(url="https://twitter.com/user/status/123456")
        files = src.list_videos()
        assert isinstance(files, list)
        assert len(files) == 1


# ---------------------------------------------------------------------------
# ArxivSource
# ---------------------------------------------------------------------------


class TestArxivSource:
    def test_import(self):
        from video_processor.sources.arxiv_source import ArxivSource

        assert ArxivSource is not None

    def test_constructor(self):
        from video_processor.sources.arxiv_source import ArxivSource

        src = ArxivSource(url_or_id="2301.07041")
        assert src.arxiv_id == "2301.07041"

    def test_constructor_from_url(self):
        from video_processor.sources.arxiv_source import ArxivSource

        src = ArxivSource(url_or_id="https://arxiv.org/abs/2301.07041v2")
        assert src.arxiv_id == "2301.07041v2"

    def test_constructor_invalid(self):
        from video_processor.sources.arxiv_source import ArxivSource

        with pytest.raises(ValueError, match="Could not extract"):
            ArxivSource(url_or_id="not-an-arxiv-id")

    def test_authenticate(self):
        from video_processor.sources.arxiv_source import ArxivSource

        src = ArxivSource(url_or_id="2301.07041")
        assert src.authenticate() is True

    @patch("requests.get")
    def test_list_videos(self, mock_get):
        from video_processor.sources.arxiv_source import ArxivSource

        atom_xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry>
            <title>Test Paper</title>
            <summary>Abstract text here.</summary>
            <author><name>Author One</name></author>
            <published>2023-01-15T00:00:00Z</published>
          </entry>
        </feed>"""
        mock_resp = MagicMock()
        mock_resp.text = atom_xml
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        src = ArxivSource(url_or_id="2301.07041")
        files = src.list_videos()
        assert isinstance(files, list)
        assert len(files) == 2  # metadata + pdf


# ---------------------------------------------------------------------------
# S3Source
# ---------------------------------------------------------------------------


class TestS3Source:
    def test_import(self):
        from video_processor.sources.s3_source import S3Source

        assert S3Source is not None

    def test_constructor(self):
        from video_processor.sources.s3_source import S3Source

        src = S3Source(bucket="my-bucket", prefix="videos/", region="us-east-1")
        assert src.bucket == "my-bucket"
        assert src.prefix == "videos/"
        assert src.region == "us-east-1"

    def test_authenticate_success(self):
        from video_processor.sources.s3_source import S3Source

        mock_client = MagicMock()
        mock_client.head_bucket.return_value = {}
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_client

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            src = S3Source(bucket="my-bucket")
            assert src.authenticate() is True

    def test_authenticate_failure(self):
        from video_processor.sources.s3_source import S3Source

        mock_client = MagicMock()
        mock_client.head_bucket.side_effect = Exception("Access Denied")
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_client

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            src = S3Source(bucket="bad-bucket")
            assert src.authenticate() is False

    def test_list_videos(self):
        from video_processor.sources.s3_source import S3Source

        mock_client = MagicMock()
        mock_client.head_bucket.return_value = {}
        paginator = MagicMock()
        mock_client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "videos/clip.mp4", "Size": 5000},
                    {"Key": "videos/notes.txt", "Size": 100},
                    {"Key": "videos/movie.mkv", "Size": 90000},
                ]
            }
        ]
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_client

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            src = S3Source(bucket="my-bucket")
            src.authenticate()
            files = src.list_videos()
            assert isinstance(files, list)
            # Only .mp4 and .mkv are video extensions
            assert len(files) == 2
            names = [f.name for f in files]
            assert "clip.mp4" in names
            assert "movie.mkv" in names


# ---------------------------------------------------------------------------
# GWSSource
# ---------------------------------------------------------------------------


class TestGWSSource:
    def test_import(self):
        from video_processor.sources.gws_source import GWSSource

        assert GWSSource is not None

    def test_constructor_defaults(self):
        from video_processor.sources.gws_source import GWSSource

        src = GWSSource()
        assert src.folder_id is None
        assert src.query is None
        assert src.doc_ids == []

    def test_constructor_with_folder(self):
        from video_processor.sources.gws_source import GWSSource

        src = GWSSource(folder_id="1abc", query="name contains 'spec'")
        assert src.folder_id == "1abc"
        assert src.query == "name contains 'spec'"

    def test_constructor_with_doc_ids(self):
        from video_processor.sources.gws_source import GWSSource

        src = GWSSource(doc_ids=["doc1", "doc2"])
        assert src.doc_ids == ["doc1", "doc2"]

    @patch("shutil.which", return_value=None)
    def test_authenticate_no_gws(self, _mock_which):
        from video_processor.sources.gws_source import GWSSource

        src = GWSSource()
        assert src.authenticate() is False

    @patch("video_processor.sources.gws_source._run_gws")
    @patch("shutil.which", return_value="/usr/local/bin/gws")
    def test_authenticate_success(self, _mock_which, mock_run):
        from video_processor.sources.gws_source import GWSSource

        mock_run.return_value = {"connectedAs": "user@example.com"}
        src = GWSSource()
        assert src.authenticate() is True

    @patch("video_processor.sources.gws_source._run_gws")
    @patch("shutil.which", return_value="/usr/local/bin/gws")
    def test_list_videos(self, _mock_which, mock_run):
        from video_processor.sources.gws_source import GWSSource

        mock_run.return_value = {
            "files": [
                {
                    "id": "doc123",
                    "name": "Project Spec",
                    "mimeType": "application/vnd.google-apps.document",
                    "modifiedTime": "2026-01-01T00:00:00Z",
                },
                {
                    "id": "sheet456",
                    "name": "Budget",
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                },
            ]
        }
        src = GWSSource(folder_id="folder1")
        files = src.list_videos()
        assert len(files) == 2
        assert files[0].name == "Project Spec"
        assert files[1].id == "sheet456"

    @patch("video_processor.sources.gws_source._run_gws")
    @patch("shutil.which", return_value="/usr/local/bin/gws")
    def test_list_videos_with_doc_ids(self, _mock_which, mock_run):
        from video_processor.sources.gws_source import GWSSource

        mock_run.return_value = {
            "id": "doc123",
            "name": "My Doc",
            "mimeType": "application/vnd.google-apps.document",
        }
        src = GWSSource(doc_ids=["doc123"])
        files = src.list_videos()
        assert len(files) == 1
        assert files[0].name == "My Doc"

    def test_result_to_source_file(self):
        from video_processor.sources.gws_source import _result_to_source_file

        sf = _result_to_source_file(
            {
                "id": "abc",
                "name": "Test Doc",
                "mimeType": "text/plain",
                "size": "1024",
                "modifiedTime": "2026-03-01",
            }
        )
        assert sf.name == "Test Doc"
        assert sf.id == "abc"
        assert sf.size_bytes == 1024
        assert sf.mime_type == "text/plain"

    @patch("video_processor.sources.gws_source._run_gws")
    def test_get_doc_text(self, mock_run):
        from video_processor.sources.gws_source import GWSSource

        mock_run.return_value = {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "Hello world\n"}},
                            ]
                        }
                    },
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "Second paragraph\n"}},
                            ]
                        }
                    },
                ]
            }
        }
        src = GWSSource()
        text = src._get_doc_text("doc123")
        assert "Hello world" in text
        assert "Second paragraph" in text

    @patch("video_processor.sources.gws_source._run_gws")
    def test_collate(self, mock_run):
        from video_processor.sources.gws_source import GWSSource

        # First call: list files, second+: export each
        mock_run.side_effect = [
            {
                "files": [
                    {
                        "id": "d1",
                        "name": "Doc A",
                        "mimeType": "application/vnd.google-apps.document",
                    },
                ]
            },
            {"raw": "Content of Doc A"},
        ]
        src = GWSSource(folder_id="f1")
        result = src.collate()
        assert "Doc A" in result
        assert "Content of Doc A" in result


# ---------------------------------------------------------------------------
# M365Source
# ---------------------------------------------------------------------------


class TestM365Source:
    def test_import(self):
        from video_processor.sources.m365_source import M365Source

        assert M365Source is not None

    def test_constructor(self):
        from video_processor.sources.m365_source import M365Source

        src = M365Source(
            web_url="https://contoso.sharepoint.com/sites/proj",
            folder_url="/sites/proj/Shared Documents",
        )
        assert src.web_url == "https://contoso.sharepoint.com/sites/proj"
        assert src.folder_url == "/sites/proj/Shared Documents"
        assert src.file_ids == []
        assert src.recursive is False

    def test_constructor_with_file_ids(self):
        from video_processor.sources.m365_source import M365Source

        src = M365Source(
            web_url="https://contoso.sharepoint.com",
            file_ids=["id1", "id2"],
        )
        assert src.file_ids == ["id1", "id2"]

    @patch("shutil.which", return_value=None)
    def test_authenticate_no_m365(self, _mock_which):
        from video_processor.sources.m365_source import M365Source

        src = M365Source(web_url="https://contoso.sharepoint.com")
        assert src.authenticate() is False

    @patch("video_processor.sources.m365_source._run_m365")
    @patch("shutil.which", return_value="/usr/local/bin/m365")
    def test_authenticate_logged_in(self, _mock_which, mock_run):
        from video_processor.sources.m365_source import M365Source

        mock_run.return_value = {"connectedAs": "user@contoso.com"}
        src = M365Source(web_url="https://contoso.sharepoint.com")
        assert src.authenticate() is True

    @patch("video_processor.sources.m365_source._run_m365")
    @patch("shutil.which", return_value="/usr/local/bin/m365")
    def test_authenticate_not_logged_in(self, _mock_which, mock_run):
        from video_processor.sources.m365_source import M365Source

        mock_run.return_value = {}
        src = M365Source(web_url="https://contoso.sharepoint.com")
        assert src.authenticate() is False

    @patch("video_processor.sources.m365_source._run_m365")
    @patch("shutil.which", return_value="/usr/local/bin/m365")
    def test_list_videos(self, _mock_which, mock_run):
        from video_processor.sources.m365_source import M365Source

        mock_run.side_effect = [
            {"connectedAs": "user@contoso.com"},  # authenticate
            [
                {
                    "Name": "spec.docx",
                    "UniqueId": "uid-1",
                    "Length": "20480",
                    "ServerRelativeUrl": "/sites/proj/docs/spec.docx",
                },
                {
                    "Name": "budget.xlsx",
                    "UniqueId": "uid-2",
                    "Length": "10240",
                    "ServerRelativeUrl": "/sites/proj/docs/budget.xlsx",
                },
                {
                    "Name": "image.png",
                    "UniqueId": "uid-3",
                    "Length": "5000",
                    "ServerRelativeUrl": "/sites/proj/docs/image.png",
                },
            ],
        ]
        src = M365Source(
            web_url="https://contoso.sharepoint.com/sites/proj",
            folder_url="/sites/proj/docs",
        )
        src.authenticate()
        files = src.list_videos()
        # Only .docx and .xlsx match _DOC_EXTENSIONS, not .png
        assert len(files) == 2
        names = [f.name for f in files]
        assert "spec.docx" in names
        assert "budget.xlsx" in names

    @patch("video_processor.sources.m365_source._run_m365")
    def test_list_videos_with_file_ids(self, mock_run):
        from video_processor.sources.m365_source import M365Source

        mock_run.return_value = {
            "Name": "report.pdf",
            "UniqueId": "uid-1",
            "Length": "50000",
            "ServerRelativeUrl": "/sites/proj/docs/report.pdf",
        }
        src = M365Source(
            web_url="https://contoso.sharepoint.com",
            file_ids=["uid-1"],
        )
        files = src.list_videos()
        assert len(files) == 1
        assert files[0].name == "report.pdf"

    def test_result_to_source_file(self):
        from video_processor.sources.m365_source import _result_to_source_file

        sf = _result_to_source_file(
            {
                "Name": "notes.txt",
                "UniqueId": "abc-123",
                "Length": "512",
                "ServerRelativeUrl": "/sites/proj/notes.txt",
                "TimeLastModified": "2026-03-01T12:00:00Z",
            }
        )
        assert sf.name == "notes.txt"
        assert sf.id == "abc-123"
        assert sf.size_bytes == 512
        assert sf.path == "/sites/proj/notes.txt"
        assert sf.modified_at == "2026-03-01T12:00:00Z"

    def test_extract_text_txt(self, tmp_path):
        from video_processor.sources.m365_source import _extract_text

        f = tmp_path / "test.txt"
        f.write_text("Hello from a text file")
        result = _extract_text(f)
        assert result == "Hello from a text file"

    def test_extract_text_md(self, tmp_path):
        from video_processor.sources.m365_source import _extract_text

        f = tmp_path / "readme.md"
        f.write_text("# Title\n\nSome content")
        result = _extract_text(f)
        assert "Title" in result
        assert "Some content" in result

    def test_extract_text_unsupported(self, tmp_path):
        from video_processor.sources.m365_source import _extract_text

        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02")
        result = _extract_text(f)
        assert "Unsupported" in result

    def test_list_no_folder_url(self):
        from video_processor.sources.m365_source import M365Source

        src = M365Source(web_url="https://contoso.sharepoint.com")
        files = src.list_videos()
        assert files == []


# ---------------------------------------------------------------------------
# ObsidianSource
# ---------------------------------------------------------------------------


class TestObsidianSource:
    def test_import(self):
        from video_processor.sources.obsidian_source import ObsidianSource

        assert ObsidianSource is not None

    def test_constructor(self, tmp_path):
        from video_processor.sources.obsidian_source import ObsidianSource

        src = ObsidianSource(vault_path=str(tmp_path))
        assert src.vault_path == tmp_path

    def test_authenticate_with_vault(self, tmp_path):
        from video_processor.sources.obsidian_source import ObsidianSource

        (tmp_path / "note.md").write_text("# Hello")
        src = ObsidianSource(vault_path=str(tmp_path))
        assert src.authenticate() is True

    def test_authenticate_empty_dir(self, tmp_path):
        from video_processor.sources.obsidian_source import ObsidianSource

        src = ObsidianSource(vault_path=str(tmp_path))
        assert src.authenticate() is False

    def test_authenticate_nonexistent(self, tmp_path):
        from video_processor.sources.obsidian_source import ObsidianSource

        src = ObsidianSource(vault_path=str(tmp_path / "nonexistent"))
        assert src.authenticate() is False

    def test_parse_note(self, tmp_path):
        from video_processor.sources.obsidian_source import parse_note

        note_content = (
            "---\n"
            "title: Test Note\n"
            "tags: [python, testing]\n"
            "---\n"
            "# Heading One\n\n"
            "Some text with a [[Wiki Link]] and [[Another Page|alias]].\n\n"
            "Also has #tag1 and #tag2 inline tags.\n\n"
            "## Sub Heading\n\n"
            "More content here.\n"
        )
        note_file = tmp_path / "test_note.md"
        note_file.write_text(note_content)

        result = parse_note(note_file)

        assert result["frontmatter"]["title"] == "Test Note"
        assert isinstance(result["frontmatter"]["tags"], list)
        assert "python" in result["frontmatter"]["tags"]
        assert "Wiki Link" in result["links"]
        assert "Another Page" in result["links"]
        assert "tag1" in result["tags"]
        assert "tag2" in result["tags"]
        assert len(result["headings"]) == 2
        assert result["headings"][0]["level"] == 1
        assert result["headings"][0]["text"] == "Heading One"
        assert "Some text" in result["body"]

    def test_ingest_vault(self, tmp_path):
        from video_processor.sources.obsidian_source import ingest_vault

        (tmp_path / "note_a.md").write_text("# A\n\nLinks to [[B]].\n")
        (tmp_path / "note_b.md").write_text("# B\n\nLinks to [[A]] and [[C]].\n")

        result = ingest_vault(tmp_path)

        assert len(result["notes"]) == 2
        names = [n["name"] for n in result["notes"]]
        assert "note_a" in names
        assert "note_b" in names
        # note_a links to B, note_b links to A and C => 3 links
        assert len(result["links"]) == 3

    def test_list_videos(self, tmp_path):
        from video_processor.sources.obsidian_source import ObsidianSource

        (tmp_path / "note1.md").write_text("# Note 1")
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "note2.md").write_text("# Note 2")

        src = ObsidianSource(vault_path=str(tmp_path))
        files = src.list_videos()
        assert len(files) == 2
        assert all(f.mime_type == "text/markdown" for f in files)


# ---------------------------------------------------------------------------
# LogseqSource
# ---------------------------------------------------------------------------


class TestLogseqSource:
    def test_import(self):
        from video_processor.sources.logseq_source import LogseqSource

        assert LogseqSource is not None

    def test_constructor(self, tmp_path):
        from video_processor.sources.logseq_source import LogseqSource

        src = LogseqSource(graph_path=str(tmp_path))
        assert src.graph_path == tmp_path

    def test_authenticate_with_pages(self, tmp_path):
        from video_processor.sources.logseq_source import LogseqSource

        (tmp_path / "pages").mkdir()
        src = LogseqSource(graph_path=str(tmp_path))
        assert src.authenticate() is True

    def test_authenticate_no_pages_or_journals(self, tmp_path):
        from video_processor.sources.logseq_source import LogseqSource

        src = LogseqSource(graph_path=str(tmp_path))
        assert src.authenticate() is False

    def test_authenticate_nonexistent(self, tmp_path):
        from video_processor.sources.logseq_source import LogseqSource

        src = LogseqSource(graph_path=str(tmp_path / "nonexistent"))
        assert src.authenticate() is False

    def test_parse_page(self, tmp_path):
        from video_processor.sources.logseq_source import parse_page

        page_content = (
            "title:: My Page\n"
            "tags:: #project #important\n"
            "- Some block content\n"
            "  - Nested with [[Another Page]] link\n"
            "  - And a #todo tag\n"
            "  - Block ref ((abc12345-6789-0abc-def0-123456789abc))\n"
        )
        page_file = tmp_path / "my_page.md"
        page_file.write_text(page_content)

        result = parse_page(page_file)

        assert result["properties"]["title"] == "My Page"
        assert "Another Page" in result["links"]
        assert "todo" in result["tags"]
        assert "abc12345-6789-0abc-def0-123456789abc" in result["block_refs"]
        assert "Some block content" in result["body"]

    def test_ingest_graph(self, tmp_path):
        from video_processor.sources.logseq_source import ingest_graph

        pages_dir = tmp_path / "pages"
        pages_dir.mkdir()
        (pages_dir / "page_a.md").write_text("- Content linking [[Page B]]\n")
        (pages_dir / "page_b.md").write_text("- Content linking [[Page A]]\n")

        journals_dir = tmp_path / "journals"
        journals_dir.mkdir()
        (journals_dir / "2026_03_07.md").write_text("- Journal entry\n")

        result = ingest_graph(tmp_path)

        assert len(result["notes"]) == 3
        assert len(result["links"]) == 2

    def test_list_videos(self, tmp_path):
        from video_processor.sources.logseq_source import LogseqSource

        pages_dir = tmp_path / "pages"
        pages_dir.mkdir()
        (pages_dir / "page1.md").write_text("- content")

        src = LogseqSource(graph_path=str(tmp_path))
        files = src.list_videos()
        assert len(files) == 1
        assert files[0].mime_type == "text/markdown"


# ---------------------------------------------------------------------------
# NotionSource
# ---------------------------------------------------------------------------


class TestNotionSource:
    def test_import(self):
        from video_processor.sources.notion_source import NotionSource

        assert NotionSource is not None

    def test_constructor(self):
        from video_processor.sources.notion_source import NotionSource

        src = NotionSource(token="ntn_test123", database_id="db-1")
        assert src.token == "ntn_test123"
        assert src.database_id == "db-1"
        assert src.page_ids == []

    @patch.dict(os.environ, {}, clear=True)
    def test_authenticate_no_token(self):
        from video_processor.sources.notion_source import NotionSource

        src = NotionSource(token="")
        assert src.authenticate() is False

    @patch("requests.get")
    def test_authenticate_with_mock(self, mock_get):
        from video_processor.sources.notion_source import NotionSource

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"name": "Test Bot"}
        mock_get.return_value = mock_resp

        src = NotionSource(token="ntn_test123")
        assert src.authenticate() is True

    @patch("requests.post")
    def test_list_videos_database(self, mock_post):
        from video_processor.sources.notion_source import NotionSource

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "page-1",
                    "last_edited_time": "2026-03-01T00:00:00Z",
                    "properties": {
                        "Name": {
                            "type": "title",
                            "title": [{"plain_text": "Meeting Notes"}],
                        }
                    },
                },
            ],
            "has_more": False,
        }
        mock_post.return_value = mock_resp

        src = NotionSource(token="ntn_test", database_id="db-1")
        files = src.list_videos()
        assert len(files) == 1
        assert files[0].name == "Meeting Notes"
        assert files[0].id == "page-1"

    def test_blocks_to_text(self):
        from video_processor.sources.notion_source import NotionSource

        src = NotionSource(token="test")
        blocks = [
            {
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"plain_text": "Title"}],
                },
            },
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"plain_text": "Some paragraph text."}],
                },
            },
            {
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"plain_text": "A bullet point"}],
                },
            },
            {
                "type": "divider",
                "divider": {},
            },
        ]
        result = src._blocks_to_text(blocks)
        assert "# Title" in result
        assert "Some paragraph text." in result
        assert "- A bullet point" in result
        assert "---" in result


# ---------------------------------------------------------------------------
# AppleNotesSource
# ---------------------------------------------------------------------------


class TestAppleNotesSource:
    def test_import(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        assert AppleNotesSource is not None

    def test_constructor(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        src = AppleNotesSource(folder="Work")
        assert src.folder == "Work"

    def test_constructor_default(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        src = AppleNotesSource()
        assert src.folder is None

    def test_authenticate_platform(self):
        import sys

        from video_processor.sources.apple_notes_source import AppleNotesSource

        src = AppleNotesSource()
        result = src.authenticate()
        if sys.platform == "darwin":
            assert result is True
        else:
            assert result is False

    def test_html_to_text(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        html = (
            "<div>Hello <b>World</b></div>"
            "<p>Paragraph one.</p>"
            "<p>Paragraph two with &amp; entity.</p>"
            "<br/>"
            "<ul><li>Item 1</li><li>Item 2</li></ul>"
        )
        result = AppleNotesSource._html_to_text(html)
        assert "Hello World" in result
        assert "Paragraph one." in result
        assert "Paragraph two with & entity." in result
        assert "Item 1" in result

    def test_html_to_text_empty(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        assert AppleNotesSource._html_to_text("") == ""

    def test_html_to_text_entities(self):
        from video_processor.sources.apple_notes_source import AppleNotesSource

        html = "&lt;code&gt; &quot;test&quot; &#39;single&#39; &nbsp;space"
        result = AppleNotesSource._html_to_text(html)
        assert "<code>" in result
        assert '"test"' in result
        assert "'single'" in result


# ---------------------------------------------------------------------------
# GoogleKeepSource
# ---------------------------------------------------------------------------


class TestGoogleKeepSource:
    def test_import(self):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        assert GoogleKeepSource is not None

    def test_constructor(self):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        src = GoogleKeepSource(label="meetings")
        assert src.label == "meetings"

    def test_constructor_default(self):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        src = GoogleKeepSource()
        assert src.label is None

    @patch("shutil.which", return_value=None)
    def test_authenticate_no_gws(self, _mock_which):
        from video_processor.sources.google_keep_source import GoogleKeepSource

        src = GoogleKeepSource()
        assert src.authenticate() is False

    def test_note_to_text(self):
        from video_processor.sources.google_keep_source import _note_to_text

        note = {
            "title": "Shopping List",
            "body": "Remember to buy groceries",
            "listContent": [
                {"text": "Milk", "checked": True},
                {"text": "Bread", "checked": False},
                {"text": "", "checked": False},
            ],
        }
        result = _note_to_text(note)
        assert "Shopping List" in result
        assert "Remember to buy groceries" in result
        assert "- [x] Milk" in result
        assert "- [ ] Bread" in result

    def test_note_to_text_empty(self):
        from video_processor.sources.google_keep_source import _note_to_text

        assert _note_to_text({}) == ""

    def test_note_to_text_text_content(self):
        from video_processor.sources.google_keep_source import _note_to_text

        note = {"title": "Simple", "textContent": "Just a plain note"}
        result = _note_to_text(note)
        assert "Simple" in result
        assert "Just a plain note" in result


# ---------------------------------------------------------------------------
# OneNoteSource
# ---------------------------------------------------------------------------


class TestOneNoteSource:
    def test_import(self):
        from video_processor.sources.onenote_source import OneNoteSource

        assert OneNoteSource is not None

    def test_constructor(self):
        from video_processor.sources.onenote_source import OneNoteSource

        src = OneNoteSource(notebook_name="Work Notes", section_name="Meetings")
        assert src.notebook_name == "Work Notes"
        assert src.section_name == "Meetings"

    def test_constructor_default(self):
        from video_processor.sources.onenote_source import OneNoteSource

        src = OneNoteSource()
        assert src.notebook_name is None
        assert src.section_name is None

    @patch("shutil.which", return_value=None)
    def test_authenticate_no_m365(self, _mock_which):
        from video_processor.sources.onenote_source import OneNoteSource

        src = OneNoteSource()
        assert src.authenticate() is False

    def test_html_to_text(self):
        from video_processor.sources.onenote_source import _html_to_text

        html = (
            "<html><body>"
            "<h1>Meeting Notes</h1>"
            "<p>Discussed the &amp; project.</p>"
            "<script>var x = 1;</script>"
            "<style>.foo { color: red; }</style>"
            "<ul><li>Action item 1</li><li>Action item 2</li></ul>"
            "<p>Entity &#x41; and &#65; decoded.</p>"
            "</body></html>"
        )
        result = _html_to_text(html)
        assert "Meeting Notes" in result
        assert "Discussed the & project." in result
        assert "var x" not in result
        assert ".foo" not in result
        assert "Action item 1" in result
        assert "Entity A and A decoded." in result

    def test_html_to_text_empty(self):
        from video_processor.sources.onenote_source import _html_to_text

        assert _html_to_text("") == ""

    def test_html_to_text_entities(self):
        from video_processor.sources.onenote_source import _html_to_text

        html = "&lt;tag&gt; &quot;quoted&quot; &apos;apos&apos; &nbsp;space"
        result = _html_to_text(html)
        assert "<tag>" in result
        assert '"quoted"' in result
        assert "'apos'" in result


# ---------------------------------------------------------------------------
# ZoomSource
# ---------------------------------------------------------------------------


class TestZoomSource:
    def test_import(self):
        from video_processor.sources.zoom_source import ZoomSource

        assert ZoomSource is not None

    def test_constructor_defaults(self):
        from video_processor.sources.zoom_source import ZoomSource

        src = ZoomSource()
        assert src.client_id is None or isinstance(src.client_id, str)
        assert src._access_token is None

    def test_constructor_explicit(self):
        from video_processor.sources.zoom_source import ZoomSource

        src = ZoomSource(
            client_id="cid",
            client_secret="csec",
            account_id="aid",
        )
        assert src.client_id == "cid"
        assert src.client_secret == "csec"
        assert src.account_id == "aid"

    def test_authenticate_no_credentials(self):
        from video_processor.sources.zoom_source import ZoomSource

        src = ZoomSource(client_id=None, client_secret=None, account_id=None)
        # No saved token, no account_id, no client_id → should fail
        assert src.authenticate() is False

    def test_list_videos_not_authenticated(self):
        from video_processor.sources.zoom_source import ZoomSource

        src = ZoomSource()
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src.list_videos()

    def test_download_not_authenticated(self):
        from video_processor.sources.zoom_source import ZoomSource

        src = ZoomSource()
        sf = SourceFile(name="test.mp4", id="123")
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src.download(sf, "/tmp/test.mp4")

    def test_fetch_transcript_not_authenticated(self):
        from video_processor.sources.zoom_source import ZoomSource

        src = ZoomSource()
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src.fetch_transcript("meeting123")

    def test_mime_types_mapping(self):
        from video_processor.sources.zoom_source import _MIME_TYPES

        assert _MIME_TYPES["MP4"] == "video/mp4"
        assert _MIME_TYPES["TRANSCRIPT"] == "text/vtt"
        assert _MIME_TYPES["M4A"] == "audio/mp4"


# ---------------------------------------------------------------------------
# TeamsRecordingSource
# ---------------------------------------------------------------------------


class TestTeamsRecordingSource:
    def test_import(self):
        from video_processor.sources.teams_recording_source import (
            TeamsRecordingSource,
        )

        assert TeamsRecordingSource is not None

    def test_constructor_default(self):
        from video_processor.sources.teams_recording_source import (
            TeamsRecordingSource,
        )

        src = TeamsRecordingSource()
        assert src.user_id == "me"

    def test_constructor_custom_user(self):
        from video_processor.sources.teams_recording_source import (
            TeamsRecordingSource,
        )

        src = TeamsRecordingSource(user_id="user@example.com")
        assert src.user_id == "user@example.com"

    @patch("shutil.which", return_value=None)
    def test_authenticate_no_m365(self, _mock_which):
        from video_processor.sources.teams_recording_source import (
            TeamsRecordingSource,
        )

        src = TeamsRecordingSource()
        assert src.authenticate() is False

    def test_vtt_to_text(self):
        from video_processor.sources.teams_recording_source import (
            _vtt_to_text,
        )

        vtt = (
            "WEBVTT\n\n"
            "1\n"
            "00:00:01.000 --> 00:00:05.000\n"
            "<v Speaker1>Hello everyone\n\n"
            "2\n"
            "00:00:05.000 --> 00:00:10.000\n"
            "<v Speaker2>Welcome to the meeting\n"
        )
        result = _vtt_to_text(vtt)
        assert "Hello everyone" in result
        assert "Welcome to the meeting" in result
        assert "WEBVTT" not in result
        assert "-->" not in result

    def test_vtt_to_text_empty(self):
        from video_processor.sources.teams_recording_source import (
            _vtt_to_text,
        )

        assert _vtt_to_text("") == ""

    def test_vtt_to_text_deduplicates(self):
        from video_processor.sources.teams_recording_source import (
            _vtt_to_text,
        )

        vtt = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:03.000\n"
            "Same line\n\n"
            "00:00:03.000 --> 00:00:05.000\n"
            "Same line\n"
        )
        result = _vtt_to_text(vtt)
        assert result.count("Same line") == 1

    def test_extract_meetings_list_dict(self):
        from video_processor.sources.teams_recording_source import (
            TeamsRecordingSource,
        )

        src = TeamsRecordingSource()
        result = src._extract_meetings_list({"value": [{"id": "m1"}]})
        assert len(result) == 1

    def test_extract_meetings_list_list(self):
        from video_processor.sources.teams_recording_source import (
            TeamsRecordingSource,
        )

        src = TeamsRecordingSource()
        result = src._extract_meetings_list([{"id": "m1"}])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# MeetRecordingSource
# ---------------------------------------------------------------------------


class TestMeetRecordingSource:
    def test_import(self):
        from video_processor.sources.meet_recording_source import (
            MeetRecordingSource,
        )

        assert MeetRecordingSource is not None

    def test_constructor_default(self):
        from video_processor.sources.meet_recording_source import (
            MeetRecordingSource,
        )

        src = MeetRecordingSource()
        assert src.drive_folder_id is None

    def test_constructor_with_folder(self):
        from video_processor.sources.meet_recording_source import (
            MeetRecordingSource,
        )

        src = MeetRecordingSource(drive_folder_id="folder123")
        assert src.drive_folder_id == "folder123"

    @patch("shutil.which", return_value=None)
    def test_authenticate_no_gws(self, _mock_which):
        from video_processor.sources.meet_recording_source import (
            MeetRecordingSource,
        )

        src = MeetRecordingSource()
        assert src.authenticate() is False

    def test_find_matching_transcript_date_extraction(self):
        import re

        name = "Meet Recording 2026-03-07T14:30:00"
        match = re.search(r"\d{4}-\d{2}-\d{2}", name)
        assert match is not None
        assert match.group(0) == "2026-03-07"

    def test_lazy_import(self):
        from video_processor.sources import MeetRecordingSource

        assert MeetRecordingSource is not None

    def test_teams_lazy_import(self):
        from video_processor.sources import TeamsRecordingSource

        assert TeamsRecordingSource is not None

    def test_zoom_lazy_import(self):
        from video_processor.sources import ZoomSource

        assert ZoomSource is not None

    def test_invalid_lazy_import(self):
        from video_processor import sources

        with pytest.raises(AttributeError):
            _ = sources.NonexistentSource


# ---------------------------------------------------------------------------
# BaseSource.download_all
# ---------------------------------------------------------------------------


class TestBaseSourceDownloadAll:
    def test_download_all_success(self, tmp_path):
        """download_all should download all files using path when available."""

        class FakeSource(BaseSource):
            def authenticate(self):
                return True

            def list_videos(self, **kwargs):
                return []

            def download(self, file, destination):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(f"content:{file.name}")
                return destination

        src = FakeSource()
        files = [
            SourceFile(name="a.mp4", id="1"),
            SourceFile(name="b.mp4", id="2", path="subdir/b.mp4"),
        ]
        paths = src.download_all(files, tmp_path)
        assert len(paths) == 2
        assert (tmp_path / "a.mp4").read_text() == "content:a.mp4"
        assert (tmp_path / "subdir" / "b.mp4").read_text() == "content:b.mp4"

    def test_download_all_partial_failure(self, tmp_path):
        """download_all should continue past failures and return successful paths."""

        class PartialFail(BaseSource):
            def authenticate(self):
                return True

            def list_videos(self, **kwargs):
                return []

            def download(self, file, destination):
                if file.id == "bad":
                    raise RuntimeError("download failed")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("ok")
                return destination

        src = PartialFail()
        files = [
            SourceFile(name="good.mp4", id="good"),
            SourceFile(name="bad.mp4", id="bad"),
            SourceFile(name="also_good.mp4", id="good2"),
        ]
        paths = src.download_all(files, tmp_path)
        assert len(paths) == 2


# ---------------------------------------------------------------------------
# Download & error handling tests
# ---------------------------------------------------------------------------


class TestRSSSourceDownload:
    @patch("requests.get")
    def test_download_entry(self, mock_get, tmp_path):
        from video_processor.sources.rss_source import RSSSource

        xml = (
            "<rss><channel><item><title>Post 1</title>"
            "<link>https://example.com/1</link>"
            "<description>Summary here</description>"
            "<pubDate>Mon, 01 Jan 2025</pubDate></item></channel></rss>"
        )
        mock_get.return_value = MagicMock(text=xml, status_code=200)
        mock_get.return_value.raise_for_status = MagicMock()

        src = RSSSource(url="https://example.com/feed.xml")
        with patch.dict("sys.modules", {"feedparser": None}):
            files = src.list_videos()
        assert len(files) == 1

        dest = tmp_path / "entry.txt"
        result = src.download(files[0], dest)
        assert result.exists()
        content = result.read_text()
        assert "Post 1" in content
        assert "Summary here" in content

    @patch("requests.get")
    def test_download_not_found(self, mock_get, tmp_path):
        from video_processor.sources.rss_source import RSSSource

        xml = "<rss><channel></channel></rss>"
        mock_get.return_value = MagicMock(text=xml, status_code=200)
        mock_get.return_value.raise_for_status = MagicMock()

        src = RSSSource(url="https://example.com/feed.xml")
        with patch.dict("sys.modules", {"feedparser": None}):
            src.list_videos()

        fake = SourceFile(name="missing", id="nonexistent")
        with pytest.raises(ValueError, match="Entry not found"):
            src.download(fake, tmp_path / "out.txt")


class TestWebSourceDownload:
    @patch("requests.get")
    def test_download_saves_text(self, mock_get, tmp_path):
        from video_processor.sources.web_source import WebSource

        mock_get.return_value = MagicMock(
            text="<html><body><p>Page content</p></body></html>", status_code=200
        )
        mock_get.return_value.raise_for_status = MagicMock()

        src = WebSource(url="https://example.com/page")
        with patch.dict("sys.modules", {"bs4": None}):
            file = src.list_videos()[0]
            dest = tmp_path / "page.txt"
            result = src.download(file, dest)
        assert result.exists()
        assert "Page content" in result.read_text()

    def test_strip_html_tags(self):
        from video_processor.sources.web_source import _strip_html_tags

        html = "<p>Hello</p><script>evil()</script><style>.x{}</style>"
        text = _strip_html_tags(html)
        assert "Hello" in text
        assert "evil" not in text


class TestHackerNewsSourceDownload:
    @patch("requests.get")
    def test_download(self, mock_get, tmp_path):
        from video_processor.sources.hackernews_source import HackerNewsSource

        story = {"title": "Story", "by": "user", "score": 1, "kids": []}

        def side_effect(url, timeout=10):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = story
            return resp

        mock_get.side_effect = side_effect

        src = HackerNewsSource(item_id=12345)
        file = src.list_videos()[0]
        dest = tmp_path / "hn.txt"
        result = src.download(file, dest)
        assert result.exists()
        assert "Story" in result.read_text()

    @patch("requests.get")
    def test_max_comments(self, mock_get):
        from video_processor.sources.hackernews_source import HackerNewsSource

        story = {"title": "Big", "by": "u", "score": 1, "kids": list(range(100, 110))}
        comment = {"by": "c", "text": "hi", "kids": []}

        def side_effect(url, timeout=10):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "/12345.json" in url:
                resp.json.return_value = story
            else:
                resp.json.return_value = comment
            return resp

        mock_get.side_effect = side_effect

        src = HackerNewsSource(item_id=12345, max_comments=3)
        text = src.fetch_text()
        assert text.count("**c**") == 3

    @patch("requests.get")
    def test_deleted_comments_skipped(self, mock_get):
        from video_processor.sources.hackernews_source import HackerNewsSource

        story = {"title": "Story", "by": "u", "score": 1, "kids": [200, 201]}

        def side_effect(url, timeout=10):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "/12345.json" in url:
                resp.json.return_value = story
            elif "/200.json" in url:
                resp.json.return_value = {"deleted": True}
            elif "/201.json" in url:
                resp.json.return_value = {"by": "alive", "text": "here", "dead": False}
            return resp

        mock_get.side_effect = side_effect

        src = HackerNewsSource(item_id=12345)
        text = src.fetch_text()
        assert "alive" in text
        assert text.count("**") == 2  # only the alive comment


class TestRedditSourceDownload:
    @patch("requests.get")
    def test_download(self, mock_get, tmp_path):
        from video_processor.sources.reddit_source import RedditSource

        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = [
            {"data": {"children": [{"data": {"title": "Post", "author": "u", "score": 1}}]}},
            {"data": {"children": []}},
        ]

        src = RedditSource(url="https://reddit.com/r/test/comments/abc/post")
        file = src.list_videos()[0]
        dest = tmp_path / "reddit.txt"
        result = src.download(file, dest)
        assert result.exists()
        assert "Post" in result.read_text()


class TestArxivSourceDownload:
    @patch("requests.get")
    def test_download_metadata(self, mock_get, tmp_path):
        from video_processor.sources.arxiv_source import ArxivSource

        xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Paper Title</title>
            <summary>Abstract text</summary>
            <author><name>Alice</name></author>
            <published>2023-01-01</published>
          </entry>
        </feed>"""

        mock_get.return_value = MagicMock(text=xml, status_code=200)
        mock_get.return_value.raise_for_status = MagicMock()

        src = ArxivSource("2301.12345")
        files = src.list_videos()
        meta = [f for f in files if f.id.startswith("meta:")][0]
        dest = tmp_path / "paper.txt"
        result = src.download(meta, dest)
        assert result.exists()
        content = result.read_text()
        assert "Paper Title" in content
        assert "Alice" in content
        assert "Abstract text" in content


class TestPodcastSourceDownload:
    @patch("requests.get")
    def test_max_episodes(self, mock_get):
        from video_processor.sources.podcast_source import PodcastSource

        items = "".join(
            f"<item><title>Ep {i}</title>"
            f'<enclosure url="https://example.com/ep{i}.mp3" type="audio/mpeg"/></item>'
            for i in range(20)
        )
        xml = f"<rss><channel>{items}</channel></rss>"

        mock_get.return_value = MagicMock(text=xml, status_code=200)
        mock_get.return_value.raise_for_status = MagicMock()

        src = PodcastSource(feed_url="https://example.com/feed.xml", max_episodes=5)
        with patch.dict("sys.modules", {"feedparser": None}):
            files = src.list_videos()
        assert len(files) == 5


# ---------------------------------------------------------------------------
# Auth edge cases
# ---------------------------------------------------------------------------


class TestZoomSourceAuth:
    def test_saved_token_valid(self, tmp_path):
        import time

        from video_processor.sources.zoom_source import ZoomSource

        token_path = tmp_path / "token.json"

        token_path.write_text(
            json.dumps({"access_token": "valid", "expires_at": time.time() + 3600})
        )
        src = ZoomSource(token_path=token_path)
        assert src._auth_saved_token() is True
        assert src._access_token == "valid"

    def test_saved_token_expired_no_refresh(self, tmp_path):
        from video_processor.sources.zoom_source import ZoomSource

        token_path = tmp_path / "token.json"
        token_path.write_text(json.dumps({"access_token": "old", "expires_at": 0}))
        src = ZoomSource(token_path=token_path)
        assert src._auth_saved_token() is False

    @patch("video_processor.sources.zoom_source.requests")
    def test_server_to_server_success(self, mock_requests, tmp_path):
        from video_processor.sources.zoom_source import ZoomSource

        mock_requests.post.return_value = MagicMock(status_code=200)
        mock_requests.post.return_value.raise_for_status = MagicMock()
        mock_requests.post.return_value.json.return_value = {
            "access_token": "s2s_tok",
            "expires_in": 3600,
        }

        src = ZoomSource(
            client_id="cid",
            client_secret="csec",
            account_id="aid",
            token_path=tmp_path / "token.json",
        )
        assert src._auth_server_to_server() is True
        assert src._access_token == "s2s_tok"

    def test_server_to_server_no_creds(self):
        from video_processor.sources.zoom_source import ZoomSource

        src = ZoomSource(account_id="aid")
        assert src._auth_server_to_server() is False

    def test_download_no_url_raises(self):
        from video_processor.sources.zoom_source import ZoomSource

        src = ZoomSource()
        src._access_token = "tok"
        file = SourceFile(name="meeting.mp4", id="123")
        with pytest.raises(ValueError, match="No download URL"):
            src.download(file, Path("/tmp/out.mp4"))


class TestGoogleDriveSourceAuth:
    def test_is_service_account_true(self, tmp_path):
        from video_processor.sources.google_drive import GoogleDriveSource

        creds = tmp_path / "sa.json"
        creds.write_text(json.dumps({"type": "service_account"}))
        src = GoogleDriveSource(credentials_path=str(creds))
        assert src._is_service_account() is True

    def test_is_service_account_false(self, tmp_path):
        from video_processor.sources.google_drive import GoogleDriveSource

        creds = tmp_path / "oauth.json"
        creds.write_text(json.dumps({"type": "authorized_user"}))
        src = GoogleDriveSource(credentials_path=str(creds))
        assert src._is_service_account() is False

    def test_is_service_account_no_file(self):
        from video_processor.sources.google_drive import GoogleDriveSource

        with patch.dict("os.environ", {}, clear=True):
            src = GoogleDriveSource(credentials_path=None)
        src.credentials_path = None
        assert src._is_service_account() is False

    def test_download_not_authed(self):
        from video_processor.sources.google_drive import GoogleDriveSource

        src = GoogleDriveSource()
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src.download(SourceFile(name="x", id="y"), Path("/tmp/x"))


class TestDropboxSourceAuth:
    def test_init_from_env(self):
        from video_processor.sources.dropbox_source import DropboxSource

        with patch.dict(
            "os.environ",
            {"DROPBOX_ACCESS_TOKEN": "tok", "DROPBOX_APP_KEY": "key"},
        ):
            src = DropboxSource()
        assert src.access_token == "tok"
        assert src.app_key == "key"

    def test_not_authed_list(self):
        from video_processor.sources.dropbox_source import DropboxSource

        src = DropboxSource()
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src.list_videos()

    def test_not_authed_download(self):
        from video_processor.sources.dropbox_source import DropboxSource

        src = DropboxSource()
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src.download(SourceFile(name="x", id="y"), Path("/tmp/x"))


class TestNotionSourceAuth:
    def test_no_token(self):
        from video_processor.sources.notion_source import NotionSource

        with patch.dict("os.environ", {}, clear=True):
            src = NotionSource(token="")
        assert src.authenticate() is False

    @patch("video_processor.sources.notion_source.requests")
    def test_auth_success(self, mock_requests):
        from video_processor.sources.notion_source import NotionSource

        mock_requests.get.return_value = MagicMock(status_code=200)
        mock_requests.get.return_value.raise_for_status = MagicMock()
        mock_requests.get.return_value.json.return_value = {"name": "Bot"}
        mock_requests.RequestException = Exception

        src = NotionSource(token="ntn_valid")
        assert src.authenticate() is True

    @patch("video_processor.sources.notion_source.requests")
    def test_auth_failure(self, mock_requests):
        from video_processor.sources.notion_source import NotionSource

        mock_requests.get.return_value.raise_for_status.side_effect = Exception("401")
        mock_requests.RequestException = Exception

        src = NotionSource(token="ntn_bad")
        assert src.authenticate() is False

    def test_extract_property_values(self):
        from video_processor.sources.notion_source import _extract_property_value

        assert _extract_property_value({"type": "number", "number": 42}) == "42"
        assert _extract_property_value({"type": "number", "number": None}) == ""
        assert _extract_property_value({"type": "select", "select": {"name": "High"}}) == "High"
        assert _extract_property_value({"type": "select", "select": None}) == ""
        assert _extract_property_value({"type": "checkbox", "checkbox": True}) == "True"
        assert _extract_property_value({"type": "url", "url": "https://ex.com"}) == "https://ex.com"
        assert _extract_property_value({"type": "unknown"}) == ""


class TestGitHubSourceAuth:
    def test_authenticate_no_token(self):
        from video_processor.sources.github_source import GitHubSource

        src = GitHubSource(repo="owner/repo")
        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = src.authenticate()
        assert result is True  # works for public repos

    @patch("requests.get")
    def test_list_excludes_pr_from_issues(self, mock_get):
        from video_processor.sources.github_source import GitHubSource

        def side_effect(url, **kwargs):
            resp = MagicMock()
            resp.ok = True
            if "/readme" in url:
                resp.json.return_value = {}
            elif "/issues" in url:
                resp.json.return_value = [
                    {"number": 1, "title": "Bug"},
                    {"number": 2, "title": "PR as issue", "pull_request": {}},
                ]
            elif "/pulls" in url:
                resp.json.return_value = []
            return resp

        mock_get.side_effect = side_effect

        src = GitHubSource(repo="o/r")
        src.authenticate()
        files = src.list_videos()
        ids = [f.id for f in files]
        assert "issue:1" in ids
        assert "issue:2" not in ids  # excluded because it has pull_request key


class TestS3SourceErrors:
    def test_not_authed_list(self):
        from video_processor.sources.s3_source import S3Source

        src = S3Source(bucket="test")
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src.list_videos()

    def test_not_authed_download(self):
        from video_processor.sources.s3_source import S3Source

        src = S3Source(bucket="test")
        with pytest.raises(RuntimeError, match="Not authenticated"):
            src.download(SourceFile(name="x", id="x"), Path("/tmp/x"))
