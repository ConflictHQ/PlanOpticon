"""Google Keep source connector using the gws CLI (googleworkspace/cli).

Fetches notes from Google Keep via the `gws` CLI tool.
Outputs plain text suitable for KG ingestion.

Requires: npm install -g @googleworkspace/cli
Auth:     gws auth login (interactive) or GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE (headless)
"""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)


def _run_gws(args: List[str], timeout: int = 30) -> Dict[str, Any]:
    """Run a gws CLI command and return parsed JSON output."""
    cmd = ["gws"] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"gws {' '.join(args)} failed: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"raw": proc.stdout.strip()}


def _note_to_text(note: dict) -> str:
    """Extract text content from a Google Keep note structure.

    Handles plain text notes and checklists. Checklist items are formatted
    as ``- [x] item`` (checked) or ``- [ ] item`` (unchecked).
    """
    parts: List[str] = []

    title = note.get("title", "").strip()
    if title:
        parts.append(title)

    body = note.get("body", note.get("textContent", "")).strip()
    if body:
        parts.append(body)

    # Checklist items may appear under "list", "listContent", or "checklistItems"
    list_items = note.get("list", note.get("listContent", note.get("checklistItems", [])))
    if isinstance(list_items, list):
        for item in list_items:
            text = item.get("text", "").strip()
            if not text:
                continue
            checked = item.get("checked", item.get("isChecked", False))
            marker = "[x]" if checked else "[ ]"
            parts.append(f"- {marker} {text}")

    return "\n\n".join(parts) if parts else ""


class GoogleKeepSource(BaseSource):
    """
    Fetch notes from Google Keep via the gws CLI.

    Usage:
        source = GoogleKeepSource()                   # all notes
        source = GoogleKeepSource(label="meetings")   # filter by label
        files = source.list_videos()
        source.download_all(files, Path("./notes"))
    """

    def __init__(self, label: Optional[str] = None):
        self.label = label

    def authenticate(self) -> bool:
        """Check if gws CLI is installed and authenticated."""
        if not shutil.which("gws"):
            logger.error("gws CLI not found. Install with: npm install -g @googleworkspace/cli")
            return False
        try:
            _run_gws(["auth", "status"], timeout=10)
            return True
        except (RuntimeError, subprocess.TimeoutExpired):
            logger.error("gws not authenticated. Run: gws auth login")
            return False

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List notes in Google Keep. Returns SourceFile per note."""
        args = ["keep", "notes", "list", "--output", "json"]

        if self.label:
            args.extend(["--label", self.label])

        try:
            result = _run_gws(args, timeout=60)
        except RuntimeError as e:
            logger.error(f"Failed to list Keep notes: {e}")
            return []

        # Result may be a list directly or nested under a key
        notes: List[dict] = []
        if isinstance(result, list):
            notes = result
        elif isinstance(result, dict):
            notes = result.get("notes", result.get("items", []))
            # If we got a single note back (not a list), wrap it
            if not notes and "id" in result and "raw" not in result:
                notes = [result]

        files: List[SourceFile] = []
        for note in notes:
            note_id = note.get("id", note.get("noteId", ""))
            title = note.get("title", "Untitled Note").strip() or "Untitled Note"
            modified = note.get("modifiedTime", note.get("updateTime"))

            # Estimate size from text content
            text = _note_to_text(note)
            size = len(text.encode("utf-8")) if text else None

            files.append(
                SourceFile(
                    name=title,
                    id=str(note_id),
                    size_bytes=size,
                    mime_type="text/plain",
                    modified_at=modified,
                )
            )

        logger.info(f"Found {len(files)} note(s) in Google Keep")
        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download a Keep note's content as a text file."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = _run_gws(
                [
                    "keep",
                    "notes",
                    "get",
                    "--params",
                    json.dumps({"noteId": file.id}),
                ],
                timeout=30,
            )
        except RuntimeError as e:
            raise RuntimeError(f"Failed to fetch Keep note {file.id}: {e}") from e

        # result may be the note dict directly or wrapped
        note = result if isinstance(result, dict) else {}
        text = _note_to_text(note)

        if not text:
            # Fallback: use raw output if structured extraction yielded nothing
            text = note.get("raw", json.dumps(note, indent=2))

        destination.write_text(text, encoding="utf-8")
        logger.info(f"Saved note '{file.name}' to {destination}")
        return destination
