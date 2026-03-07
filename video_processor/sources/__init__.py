"""Cloud and web source integrations for fetching content from remote sources."""

from video_processor.sources.base import BaseSource, SourceFile

__all__ = [
    "BaseSource",
    "SourceFile",
    "ArxivSource",
    "GitHubSource",
    "GoogleDriveSource",
    "HackerNewsSource",
    "PodcastSource",
    "RedditSource",
    "RSSSource",
    "TwitterSource",
    "GWSSource",
    "M365Source",
    "WebSource",
    "YouTubeSource",
]


def __getattr__(name: str):
    """Lazy imports to avoid pulling in optional dependencies at import time."""
    _lazy_map = {
        "ArxivSource": "video_processor.sources.arxiv_source",
        "GitHubSource": "video_processor.sources.github_source",
        "GoogleDriveSource": "video_processor.sources.google_drive",
        "GWSSource": "video_processor.sources.gws_source",
        "M365Source": "video_processor.sources.m365_source",
        "HackerNewsSource": "video_processor.sources.hackernews_source",
        "PodcastSource": "video_processor.sources.podcast_source",
        "RedditSource": "video_processor.sources.reddit_source",
        "RSSSource": "video_processor.sources.rss_source",
        "TwitterSource": "video_processor.sources.twitter_source",
        "WebSource": "video_processor.sources.web_source",
        "YouTubeSource": "video_processor.sources.youtube_source",
    }
    if name in _lazy_map:
        import importlib

        module = importlib.import_module(_lazy_map[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
