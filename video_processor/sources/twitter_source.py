"""Twitter/X source connector -- stub requiring auth or gallery-dl."""

import logging
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)


class TwitterSource(BaseSource):
    """
    Fetch Twitter/X posts and threads.

    Twitter API v2 requires authentication. This connector attempts to use
    gallery-dl as a fallback for public tweets.

    Auth options:
    - Set TWITTER_BEARER_TOKEN env var for API v2 access
    - Install gallery-dl for scraping public tweets: pip install gallery-dl
    """

    def __init__(self, url: str):
        self.url = url
        self._bearer_token: Optional[str] = None

    def authenticate(self) -> bool:
        """Check for Twitter API token or gallery-dl availability."""
        import os

        self._bearer_token = os.environ.get("TWITTER_BEARER_TOKEN")
        if self._bearer_token:
            return True

        # Check for gallery-dl fallback
        try:
            import gallery_dl  # noqa: F401

            logger.info("Using gallery-dl for Twitter content extraction")
            return True
        except ImportError:
            pass

        logger.error(
            "Twitter source requires either:\n"
            "  1. TWITTER_BEARER_TOKEN env var (Twitter API v2)\n"
            "  2. gallery-dl installed: pip install gallery-dl\n"
            "Twitter API access: https://developer.twitter.com/en/portal/dashboard"
        )
        return False

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """Return a single SourceFile for the tweet/thread."""
        return [
            SourceFile(
                name=self.url.split("/")[-1] or "tweet",
                id=self.url,
                mime_type="text/plain",
            )
        ]

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download tweet content as text."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        text = self.fetch_text()
        destination.write_text(text, encoding="utf-8")
        logger.info(f"Saved Twitter content to {destination}")
        return destination

    def fetch_text(self) -> str:
        """Extract tweet text via API or gallery-dl."""
        if self._bearer_token:
            return self._fetch_via_api()

        try:
            return self._fetch_via_gallery_dl()
        except ImportError:
            raise RuntimeError(
                "No Twitter extraction method available. See authenticate() for setup."
            )

    def _fetch_via_api(self) -> str:
        """Fetch tweet via Twitter API v2."""
        import re

        import requests

        match = re.search(r"/status/(\d+)", self.url)
        if not match:
            raise ValueError(f"Could not extract tweet ID from: {self.url}")

        tweet_id = match.group(1)
        resp = requests.get(
            f"https://api.twitter.com/2/tweets/{tweet_id}",
            headers={"Authorization": f"Bearer {self._bearer_token}"},
            params={"tweet.fields": "author_id,created_at,text"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return f"{data.get('text', '')}\n\nCreated: {data.get('created_at', 'unknown')}"

    def _fetch_via_gallery_dl(self) -> str:
        """Use gallery-dl to extract tweet metadata."""
        import json
        import subprocess

        result = subprocess.run(
            ["gallery-dl", "--dump-json", self.url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gallery-dl failed: {result.stderr}")

        items = json.loads(result.stdout)
        texts = []
        for item in items if isinstance(items, list) else [items]:
            if isinstance(item, dict):
                texts.append(item.get("content", item.get("text", str(item))))
        return "\n\n".join(texts) if texts else "No text content extracted."
