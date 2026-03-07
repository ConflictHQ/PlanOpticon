"""arXiv source connector for fetching paper metadata and PDFs."""

import logging
import re
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)

_ARXIV_ID_PATTERN = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
ARXIV_API = "http://export.arxiv.org/api/query"


def _extract_arxiv_id(url_or_id: str) -> str:
    """Extract arXiv paper ID from a URL or bare ID string."""
    match = _ARXIV_ID_PATTERN.search(url_or_id)
    if not match:
        raise ValueError(f"Could not extract arXiv ID from: {url_or_id}")
    return match.group(0)


class ArxivSource(BaseSource):
    """
    Fetch arXiv paper metadata and PDF.

    Uses the arXiv API (Atom feed) for metadata and direct PDF download.
    Requires: pip install requests
    """

    def __init__(self, url_or_id: str):
        self.arxiv_id = _extract_arxiv_id(url_or_id)
        self._metadata: Optional[dict] = None

    def authenticate(self) -> bool:
        """No auth needed for arXiv."""
        return True

    def _fetch_metadata(self) -> dict:
        """Fetch paper metadata from the arXiv API."""
        if self._metadata:
            return self._metadata

        import xml.etree.ElementTree as ET

        import requests

        resp = requests.get(ARXIV_API, params={"id_list": self.arxiv_id}, timeout=15)
        resp.raise_for_status()

        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        root = ET.fromstring(resp.text)
        entry = root.find("atom:entry", ns)
        if entry is None:
            raise ValueError(f"Paper not found: {self.arxiv_id}")

        self._metadata = {
            "title": (entry.findtext("atom:title", namespaces=ns) or "").strip(),
            "summary": (entry.findtext("atom:summary", namespaces=ns) or "").strip(),
            "authors": [
                a.findtext("atom:name", namespaces=ns) or ""
                for a in entry.findall("atom:author", ns)
            ],
            "published": entry.findtext("atom:published", namespaces=ns) or "",
            "pdf_url": f"https://arxiv.org/pdf/{self.arxiv_id}.pdf",
        }
        return self._metadata

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """Return SourceFiles for the paper metadata and PDF."""
        meta = self._fetch_metadata()
        return [
            SourceFile(
                name=f"{meta['title']} (metadata)",
                id=f"meta:{self.arxiv_id}",
                mime_type="text/plain",
            ),
            SourceFile(
                name=f"{meta['title']}.pdf",
                id=f"pdf:{self.arxiv_id}",
                mime_type="application/pdf",
            ),
        ]

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download paper metadata as text or the PDF file."""
        import requests

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        meta = self._fetch_metadata()

        if file.id.startswith("meta:"):
            authors = ", ".join(meta["authors"])
            text = (
                f"# {meta['title']}\n\n"
                f"Authors: {authors}\n"
                f"Published: {meta['published']}\n"
                f"arXiv: {self.arxiv_id}\n\n"
                f"## Abstract\n\n{meta['summary']}"
            )
            destination.write_text(text, encoding="utf-8")
        elif file.id.startswith("pdf:"):
            resp = requests.get(meta["pdf_url"], timeout=60, stream=True)
            resp.raise_for_status()
            with open(destination, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

        logger.info(f"Downloaded arXiv {self.arxiv_id} to {destination}")
        return destination
