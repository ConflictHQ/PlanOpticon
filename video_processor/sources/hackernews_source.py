"""Hacker News source connector using the official Firebase API."""

import logging
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"


class HackerNewsSource(BaseSource):
    """
    Fetch Hacker News stories and comments via the public API.

    API docs: https://github.com/HackerNews/API
    Requires: pip install requests
    """

    def __init__(self, item_id: int, max_comments: int = 200):
        """
        Parameters
        ----------
        item_id : int
            HN story/item ID (e.g., 12345678).
        max_comments : int
            Maximum number of comments to fetch (default 200).
        """
        self.item_id = item_id
        self.max_comments = max_comments

    def authenticate(self) -> bool:
        """No auth needed for the HN API."""
        return True

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """Return a single SourceFile for the HN story."""
        return [
            SourceFile(
                name=f"hn_{self.item_id}",
                id=str(self.item_id),
                mime_type="text/plain",
            )
        ]

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download the story and comments as plain text."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        text = self.fetch_text()
        destination.write_text(text, encoding="utf-8")
        logger.info(f"Saved HN story {self.item_id} to {destination}")
        return destination

    def _get_item(self, item_id: int) -> dict:
        import requests

        resp = requests.get(f"{HN_API}/item/{item_id}.json", timeout=10)
        resp.raise_for_status()
        return resp.json() or {}

    def fetch_text(self) -> str:
        """Fetch story and comments as structured text."""
        story = self._get_item(self.item_id)
        lines = []
        lines.append(f"# {story.get('title', 'Untitled')}")
        lines.append(f"by {story.get('by', 'unknown')} | {story.get('score', 0)} points")
        if story.get("url"):
            lines.append(f"URL: {story['url']}")
        if story.get("text"):
            lines.append(f"\n{story['text']}")
        lines.append("")

        # Fetch comments
        kid_ids = story.get("kids", [])
        if kid_ids:
            lines.append("## Comments\n")
            count = [0]
            self._fetch_comments(kid_ids, lines, depth=0, count=count)

        return "\n".join(lines)

    def _fetch_comments(self, kid_ids: list, lines: list, depth: int, count: list) -> None:
        """Recursively fetch and format comments."""
        indent = "  " * depth
        for kid_id in kid_ids:
            if count[0] >= self.max_comments:
                return
            try:
                item = self._get_item(kid_id)
            except Exception:
                continue

            if item.get("deleted") or item.get("dead"):
                continue

            count[0] += 1
            author = item.get("by", "[deleted]")
            text = item.get("text", "")
            lines.append(f"{indent}**{author}**:")
            lines.append(f"{indent}{text}")
            lines.append("")

            if item.get("kids"):
                self._fetch_comments(item["kids"], lines, depth + 1, count)
