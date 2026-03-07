"""Web page source connector for fetching and extracting text from URLs."""

import logging
import re
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)


def _strip_html_tags(html: str) -> str:
    """Minimal HTML tag stripper using stdlib only."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<(nav|footer|header)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class WebSource(BaseSource):
    """
    Fetch web pages and extract main text content.

    Uses requests + BeautifulSoup (optional) for content extraction.
    Falls back to regex-based tag stripping if bs4 is unavailable.

    Requires: pip install requests (included in most environments)
    Optional:  pip install beautifulsoup4 lxml
    """

    def __init__(self, url: str):
        self.url = url
        self._content: Optional[str] = None

    def authenticate(self) -> bool:
        """No auth needed for public web pages."""
        return True

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """Return a single SourceFile representing the web page."""
        return [
            SourceFile(
                name=self.url.split("/")[-1] or "page",
                id=self.url,
                mime_type="text/html",
            )
        ]

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download and save the extracted text content."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        text = self.fetch_text()
        destination.write_text(text, encoding="utf-8")
        logger.info(f"Saved web content to {destination}")
        return destination

    def fetch_text(self) -> str:
        """Fetch the URL and extract main text content."""
        if self._content is not None:
            return self._content

        import requests

        resp = requests.get(self.url, timeout=30, headers={"User-Agent": "PlanOpticon/0.3"})
        resp.raise_for_status()

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, "html.parser")
            # Remove non-content elements
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            # Prefer <article> or <main> if present
            main = soup.find("article") or soup.find("main") or soup.find("body")
            self._content = main.get_text(separator="\n", strip=True) if main else soup.get_text()
        except ImportError:
            logger.debug("beautifulsoup4 not available, using regex fallback")
            self._content = _strip_html_tags(resp.text)

        return self._content
