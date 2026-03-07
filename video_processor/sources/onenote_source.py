"""Microsoft OneNote source connector using the m365 CLI (cli-microsoft365).

Fetches pages from OneNote notebooks via the `m365` CLI tool.
Outputs plain text suitable for KG ingestion.

Requires: npm install -g @pnp/cli-microsoft365
Auth:     m365 login (interactive)
Docs:     https://pnp.github.io/cli-microsoft365/
"""

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)


def _run_m365(args: List[str], timeout: int = 30) -> Any:
    """Run an m365 CLI command and return parsed JSON output."""
    cmd = ["m365"] + args + ["--output", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"m365 {' '.join(args)} failed: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return proc.stdout.strip()


def _html_to_text(html: str) -> str:
    """Strip HTML tags and decode entities to produce plain text.

    Uses only stdlib ``re`` — no external dependencies.
    """
    # Remove script/style blocks entirely
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace <br>, <p>, <div>, <li>, <tr> with newlines for readability
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|tr|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    entity_map = {
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&apos;": "'",
        "&nbsp;": " ",
    }
    for entity, char in entity_map.items():
        text = text.replace(entity, char)
    # Decode numeric entities (&#123; and &#x1a;)
    text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class OneNoteSource(BaseSource):
    """
    Fetch pages from OneNote notebooks via the m365 CLI.

    Usage:
        source = OneNoteSource()                                   # all notebooks
        source = OneNoteSource(notebook_name="Work Notes")         # specific notebook
        source = OneNoteSource(notebook_name="Work", section_name="Meetings")
        files = source.list_videos()
        source.download_all(files, Path("./notes"))
    """

    def __init__(
        self,
        notebook_name: Optional[str] = None,
        section_name: Optional[str] = None,
    ):
        self.notebook_name = notebook_name
        self.section_name = section_name

    def authenticate(self) -> bool:
        """Check if m365 CLI is installed and logged in."""
        if not shutil.which("m365"):
            logger.error("m365 CLI not found. Install with: npm install -g @pnp/cli-microsoft365")
            return False
        try:
            result = _run_m365(["status"], timeout=10)
            if isinstance(result, dict) and result.get("connectedAs"):
                return True
            if isinstance(result, str) and "Logged in" in result:
                return True
            logger.error("m365 not logged in. Run: m365 login")
            return False
        except (RuntimeError, subprocess.TimeoutExpired):
            logger.error("m365 not logged in. Run: m365 login")
            return False

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List OneNote pages across notebooks/sections. Returns SourceFile per page."""
        files: List[SourceFile] = []

        # Step 1: List notebooks
        try:
            notebooks = _run_m365(["onenote", "notebook", "list"], timeout=60)
        except RuntimeError as e:
            logger.error(f"Failed to list OneNote notebooks: {e}")
            return []

        if not isinstance(notebooks, list):
            notebooks = []

        # Filter notebooks by name if specified
        if self.notebook_name:
            notebooks = [
                nb
                for nb in notebooks
                if self.notebook_name.lower() in nb.get("displayName", "").lower()
            ]

        for notebook in notebooks:
            notebook_id = notebook.get("id", "")
            notebook_name = notebook.get("displayName", "Untitled Notebook")

            # Step 2: List sections in this notebook
            try:
                sections = _run_m365(
                    ["onenote", "section", "list", "--notebookId", notebook_id],
                    timeout=60,
                )
            except RuntimeError as e:
                logger.warning(f"Failed to list sections for notebook '{notebook_name}': {e}")
                continue

            if not isinstance(sections, list):
                sections = []

            # Filter sections by name if specified
            if self.section_name:
                sections = [
                    s
                    for s in sections
                    if self.section_name.lower() in s.get("displayName", "").lower()
                ]

            for section in sections:
                section_id = section.get("id", "")
                section_name = section.get("displayName", "Untitled Section")

                # Step 3: List pages in this section
                try:
                    pages = _run_m365(
                        ["onenote", "page", "list", "--sectionId", section_id],
                        timeout=60,
                    )
                except RuntimeError as e:
                    logger.warning(f"Failed to list pages in section '{section_name}': {e}")
                    continue

                if not isinstance(pages, list):
                    pages = []

                for page in pages:
                    page_id = page.get("id", "")
                    title = page.get("title", "Untitled Page").strip() or "Untitled Page"
                    modified = page.get("lastModifiedDateTime")
                    # Build a path for organizational context
                    page_path = f"{notebook_name}/{section_name}/{title}"

                    files.append(
                        SourceFile(
                            name=title,
                            id=str(page_id),
                            size_bytes=None,
                            mime_type="text/html",
                            modified_at=modified,
                            path=page_path,
                        )
                    )

        logger.info(f"Found {len(files)} page(s) in OneNote")
        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download a OneNote page's content as a text file."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = _run_m365(
                ["onenote", "page", "get", "--id", file.id],
                timeout=60,
            )
        except RuntimeError as e:
            raise RuntimeError(f"Failed to fetch OneNote page {file.id}: {e}") from e

        # Extract HTML content from the result
        if isinstance(result, dict):
            html = result.get("content", result.get("body", {}).get("content", ""))
            if not html:
                # Fallback: serialize the whole response
                html = json.dumps(result, indent=2)
        elif isinstance(result, str):
            html = result
        else:
            html = str(result)

        text = _html_to_text(html)
        destination.write_text(text, encoding="utf-8")
        logger.info(f"Saved page '{file.name}' to {destination}")
        return destination
