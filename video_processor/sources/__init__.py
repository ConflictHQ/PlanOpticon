"""Cloud, web, and notes source integrations for fetching content from remote sources."""

from video_processor.sources.base import BaseSource, SourceFile

__all__ = [
    "BaseSource",
    "SourceFile",
    "AppleNotesSource",
    "ArxivSource",
    "GitHubSource",
    "GoogleDriveSource",
    "GoogleKeepSource",
    "GWSSource",
    "HackerNewsSource",
    "LogseqSource",
    "M365Source",
    "NotionSource",
    "ObsidianSource",
    "OneNoteSource",
    "PodcastSource",
    "RedditSource",
    "RSSSource",
    "TwitterSource",
    "WebSource",
    "YouTubeSource",
]


def __getattr__(name: str):
    """Lazy imports to avoid pulling in optional dependencies at import time."""
    _lazy_map = {
        "AppleNotesSource": "video_processor.sources.apple_notes_source",
        "ArxivSource": "video_processor.sources.arxiv_source",
        "GitHubSource": "video_processor.sources.github_source",
        "GoogleDriveSource": "video_processor.sources.google_drive",
        "GoogleKeepSource": "video_processor.sources.google_keep_source",
        "GWSSource": "video_processor.sources.gws_source",
        "HackerNewsSource": "video_processor.sources.hackernews_source",
        "LogseqSource": "video_processor.sources.logseq_source",
        "M365Source": "video_processor.sources.m365_source",
        "NotionSource": "video_processor.sources.notion_source",
        "ObsidianSource": "video_processor.sources.obsidian_source",
        "OneNoteSource": "video_processor.sources.onenote_source",
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
