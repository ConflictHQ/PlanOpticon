"""Podcast feed source connector -- extends RSS for audio enclosures."""

import logging
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)


class PodcastSource(BaseSource):
    """
    Parse podcast RSS feeds and download audio episodes for pipeline processing.

    Extends the RSS pattern to extract <enclosure> audio URLs.
    Requires: pip install requests
    Optional: pip install feedparser
    """

    def __init__(self, feed_url: str, max_episodes: int = 10):
        self.feed_url = feed_url
        self.max_episodes = max_episodes
        self._episodes: List[dict] = []

    def authenticate(self) -> bool:
        """No auth needed for public podcast feeds."""
        return True

    def _parse_feed(self) -> None:
        """Fetch and parse the podcast feed for audio enclosures."""
        if self._episodes:
            return

        import requests

        resp = requests.get(self.feed_url, timeout=15, headers={"User-Agent": "PlanOpticon/0.3"})
        resp.raise_for_status()

        try:
            import feedparser

            feed = feedparser.parse(resp.text)
            for entry in feed.entries[: self.max_episodes]:
                audio_url = None
                for link in entry.get("links", []):
                    if link.get("type", "").startswith("audio/"):
                        audio_url = link.get("href")
                        break
                if not audio_url and entry.get("enclosures"):
                    audio_url = entry["enclosures"][0].get("href")
                if audio_url:
                    self._episodes.append(
                        {
                            "title": entry.get("title", "Untitled"),
                            "url": audio_url,
                            "published": entry.get("published", ""),
                            "duration": entry.get("itunes_duration", ""),
                        }
                    )
        except ImportError:
            logger.debug("feedparser not available, using xml.etree fallback")
            self._parse_xml(resp.text)

    def _parse_xml(self, text: str) -> None:
        """Fallback parser for podcast XML using stdlib."""
        import xml.etree.ElementTree as ET

        root = ET.fromstring(text)
        items = root.findall(".//item")
        for item in items[: self.max_episodes]:
            enclosure = item.find("enclosure")
            if enclosure is None:
                continue
            audio_url = enclosure.get("url", "")
            if not audio_url:
                continue
            title = item.findtext("title") or "Untitled"
            pub = item.findtext("pubDate") or ""
            self._episodes.append(
                {"title": title, "url": audio_url, "published": pub, "duration": ""}
            )

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List podcast episodes as SourceFiles."""
        self._parse_feed()
        return [
            SourceFile(
                name=ep["title"],
                id=ep["url"],
                mime_type="audio/mpeg",
                modified_at=ep["published"],
            )
            for ep in self._episodes
        ]

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download the podcast audio file."""
        import requests

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        resp = requests.get(
            file.id, timeout=60, stream=True, headers={"User-Agent": "PlanOpticon/0.3"}
        )
        resp.raise_for_status()

        with open(destination, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded podcast episode to {destination}")
        return destination
