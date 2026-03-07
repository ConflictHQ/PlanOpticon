"""Reddit source connector using the public JSON API."""

import logging
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)


class RedditSource(BaseSource):
    """
    Fetch Reddit posts and comments via the public JSON API.

    No auth required for public posts. Append .json to any Reddit URL.
    Requires: pip install requests
    """

    def __init__(self, url: str):
        """
        Parameters
        ----------
        url : str
            Reddit post or subreddit URL.
        """
        self.url = url.rstrip("/")

    def authenticate(self) -> bool:
        """No auth needed for public Reddit content."""
        return True

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """Return a single SourceFile for the Reddit post."""
        return [
            SourceFile(
                name=self.url.split("/")[-1] or "reddit_post",
                id=self.url,
                mime_type="text/plain",
            )
        ]

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download post and comments as plain text."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        text = self.fetch_text()
        destination.write_text(text, encoding="utf-8")
        logger.info(f"Saved Reddit content to {destination}")
        return destination

    def fetch_text(self) -> str:
        """Fetch the Reddit post and comments as structured text."""
        import requests

        json_url = self.url.rstrip("/") + ".json"
        resp = requests.get(
            json_url,
            timeout=15,
            headers={"User-Agent": "PlanOpticon/0.3 (source connector)"},
        )
        resp.raise_for_status()
        data = resp.json()

        lines = []
        # Post data is in first listing
        if isinstance(data, list) and len(data) > 0:
            post = data[0]["data"]["children"][0]["data"]
            lines.append(f"# {post.get('title', 'Untitled')}")
            lines.append(f"by u/{post.get('author', '[deleted]')} | {post.get('score', 0)} points")
            lines.append("")
            if post.get("selftext"):
                lines.append(post["selftext"])
                lines.append("")

            # Comments in second listing
            if len(data) > 1:
                lines.append("## Comments\n")
                self._extract_comments(data[1]["data"]["children"], lines, depth=0)

        return "\n".join(lines)

    def _extract_comments(self, children: list, lines: list, depth: int) -> None:
        """Recursively extract comment text."""
        indent = "  " * depth
        for child in children:
            if child.get("kind") != "t1":
                continue
            c = child["data"]
            author = c.get("author", "[deleted]")
            body = c.get("body", "")
            lines.append(f"{indent}**{author}** ({c.get('score', 0)} pts):")
            lines.append(f"{indent}{body}")
            lines.append("")
            # Recurse into replies
            replies = c.get("replies")
            if isinstance(replies, dict):
                self._extract_comments(replies["data"]["children"], lines, depth + 1)
