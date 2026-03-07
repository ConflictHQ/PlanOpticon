"""Apple Notes source connector via osascript (macOS only)."""

import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)


class AppleNotesSource(BaseSource):
    """
    Fetch notes from Apple Notes using osascript (AppleScript).

    Only works on macOS. Requires the Notes app to be available
    and permission for osascript to access it.
    """

    def __init__(self, folder: Optional[str] = None):
        self.folder = folder

    def authenticate(self) -> bool:
        """Check that we are running on macOS."""
        if sys.platform != "darwin":
            logger.error("Apple Notes is only available on macOS (current: %s)", sys.platform)
            return False
        return True

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List notes from Apple Notes via osascript."""
        if not self.authenticate():
            return []

        if self.folder:
            script = (
                'tell application "Notes"\n'
                "  set noteList to {}\n"
                f"  repeat with f in folders of default account\n"
                f'    if name of f is "{self.folder}" then\n'
                "      repeat with n in notes of f\n"
                '        set end of noteList to (id of n) & "|||" & (name of n)\n'
                "      end repeat\n"
                "    end if\n"
                "  end repeat\n"
                "  return noteList\n"
                "end tell"
            )
        else:
            script = (
                'tell application "Notes"\n'
                "  set noteList to {}\n"
                "  repeat with n in notes of default account\n"
                '    set end of noteList to (id of n) & "|||" & (name of n)\n'
                "  end repeat\n"
                "  return noteList\n"
                "end tell"
            )

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            logger.error("osascript not found. Apple Notes requires macOS.")
            return []
        except subprocess.TimeoutExpired:
            logger.error("osascript timed out while listing notes.")
            return []

        if result.returncode != 0:
            logger.error("Failed to list notes: %s", result.stderr.strip())
            return []

        return self._parse_note_list(result.stdout.strip())

    def _parse_note_list(self, output: str) -> List[SourceFile]:
        """Parse osascript output into SourceFile objects.

        Expected format: comma-separated items of 'id|||name' pairs.
        """
        files: List[SourceFile] = []
        if not output:
            return files

        # AppleScript returns a flat comma-separated list
        entries = output.split(", ")
        for entry in entries:
            entry = entry.strip()
            if "|||" not in entry:
                continue
            note_id, _, name = entry.partition("|||")
            note_id = note_id.strip()
            name = name.strip()
            if note_id and name:
                files.append(
                    SourceFile(
                        name=name,
                        id=note_id,
                        mime_type="text/plain",
                    )
                )

        logger.info("Found %d notes", len(files))
        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download a note's content as plain text."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        script = (
            'tell application "Notes"\n'
            f'  set theNote to note id "{file.id}" of default account\n'
            "  return body of theNote\n"
            "end tell"
        )

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            raise RuntimeError("osascript not found. Apple Notes requires macOS.")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"osascript timed out fetching note {file.id}")

        if result.returncode != 0:
            raise RuntimeError(f"Failed to fetch note {file.id}: {result.stderr.strip()}")

        html_body = result.stdout.strip()
        text = self._html_to_text(html_body)

        # Prepend title
        content = f"# {file.name}\n\n{text}"
        destination.write_text(content, encoding="utf-8")
        logger.info("Saved Apple Note to %s", destination)
        return destination

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Strip HTML tags and return plain text.

        Apple Notes returns note bodies as HTML. This uses regex-based
        stripping similar to web_source._strip_html_tags.
        """
        if not html:
            return ""
        # Replace <br> variants with newlines
        text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        # Replace block-level closing tags with newlines
        text = re.sub(r"</(?:p|div|li|tr|h[1-6])>", "\n", text, flags=re.IGNORECASE)
        # Remove all remaining tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode common HTML entities
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")
        text = text.replace("&nbsp;", " ")
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
