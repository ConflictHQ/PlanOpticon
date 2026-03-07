"""Tests for all source connectors: import, instantiation, authenticate, list_videos."""

import os
from unittest.mock import MagicMock, patch

import pytest

from video_processor.sources.base import SourceFile

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
