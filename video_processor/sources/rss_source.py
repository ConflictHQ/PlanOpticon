"""RSS/Atom feed source connector."""

import logging
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)


class RSSSource(BaseSource):
    """
    Parse RSS/Atom feeds and extract entries as text documents.

    Optional: pip install feedparser (falls back to xml.etree.ElementTree)
    Requires: pip install requests
    """

    def __init__(self, url: str, max_entries: int = 50):
        self.url = url
        self.max_entries = max_entries
        self._entries: List[dict] = []

    def authenticate(self) -> bool:
        """No auth needed for public feeds."""
        return True

    def _parse_feed(self) -> None:
        """Fetch and parse the feed."""
        if self._entries:
            return

        import requests

        resp = requests.get(self.url, timeout=15, headers={"User-Agent": "PlanOpticon/0.3"})
        resp.raise_for_status()

        try:
            import feedparser

            feed = feedparser.parse(resp.text)
            for entry in feed.entries[: self.max_entries]:
                self._entries.append(
                    {
                        "title": entry.get("title", "Untitled"),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", ""),
                        "published": entry.get("published", ""),
                        "id": entry.get("id", entry.get("link", "")),
                    }
                )
        except ImportError:
            logger.debug("feedparser not available, using xml.etree fallback")
            self._parse_xml(resp.text)

    def _parse_xml(self, text: str) -> None:
        """Fallback parser using stdlib xml.etree."""
        import xml.etree.ElementTree as ET

        root = ET.fromstring(text)
        # Handle RSS 2.0
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        for item in items[: self.max_entries]:
            title = (
                item.findtext("title") or item.findtext("atom:title", namespaces=ns) or "Untitled"
            )
            link = item.findtext("link") or ""
            if not link:
                link_el = item.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
            desc = (
                item.findtext("description") or item.findtext("atom:summary", namespaces=ns) or ""
            )
            pub = item.findtext("pubDate") or item.findtext("atom:published", namespaces=ns) or ""
            self._entries.append(
                {"title": title, "link": link, "summary": desc, "published": pub, "id": link}
            )

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List feed entries as SourceFiles."""
        self._parse_feed()
        return [
            SourceFile(
                name=e["title"], id=e["id"], mime_type="text/plain", modified_at=e["published"]
            )
            for e in self._entries
        ]

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Write an entry's content as a text file."""
        self._parse_feed()
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        entry = next((e for e in self._entries if e["id"] == file.id), None)
        if not entry:
            raise ValueError(f"Entry not found: {file.id}")

        text = (
            f"# {entry['title']}\n\n"
            f"Published: {entry['published']}\n"
            f"Link: {entry['link']}\n\n"
            f"{entry['summary']}"
        )
        destination.write_text(text, encoding="utf-8")
        logger.info(f"Saved RSS entry to {destination}")
        return destination
