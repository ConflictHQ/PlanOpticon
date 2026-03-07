"""Google Meet recording source using the gws CLI (googleworkspace/cli).

Fetches Meet recordings and companion transcripts from Google Drive
via the `gws` CLI tool.

Requires: npm install -g @googleworkspace/cli
Auth:     gws auth login (interactive) or GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE (headless)
"""

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile
from video_processor.sources.gws_source import _run_gws

logger = logging.getLogger(__name__)


class MeetRecordingSource(BaseSource):
    """
    Fetch Google Meet recordings and transcripts from Google Drive via the gws CLI.

    Meet stores recordings as MP4 files in Drive (typically in a "Meet Recordings"
    folder) and auto-generated transcripts as Google Docs.

    Usage:
        source = MeetRecordingSource()
        source.authenticate()
        recordings = source.list_videos()
        source.download_all(recordings, Path("./recordings"))

        # Fetch transcript for a specific recording
        transcript = source.fetch_transcript("Meet Recording 2026-03-07")
    """

    def __init__(self, drive_folder_id: Optional[str] = None):
        self.drive_folder_id = drive_folder_id

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
        """List Google Meet recordings in Drive.

        Searches for MP4 files with 'Meet Recording' in the name. If a
        drive_folder_id is set, restricts search to that folder.
        Also discovers companion transcript docs for each recording.
        """
        target_folder = folder_id or self.drive_folder_id
        files: List[SourceFile] = []

        # Build the Drive search query for Meet recordings
        q_parts = [
            "mimeType='video/mp4'",
            "name contains 'Meet Recording'",
            "trashed=false",
        ]
        if target_folder:
            q_parts.append(f"'{target_folder}' in parents")

        params = {
            "q": " and ".join(q_parts),
            "fields": "files(id,name,mimeType,size,modifiedTime)",
            "pageSize": 50,
            "orderBy": "modifiedTime desc",
        }

        try:
            result = _run_gws(
                [
                    "drive",
                    "files",
                    "list",
                    "--params",
                    json.dumps(params),
                ],
                timeout=60,
            )
        except RuntimeError as e:
            logger.error(f"Failed to list Meet recordings: {e}")
            return []

        recordings = result.get("files", [])
        for item in recordings:
            size = item.get("size")
            files.append(
                SourceFile(
                    name=item.get("name", "Meet Recording"),
                    id=item.get("id", ""),
                    size_bytes=int(size) if size else None,
                    mime_type=item.get("mimeType", "video/mp4"),
                    modified_at=item.get("modifiedTime"),
                )
            )

        # Also search for auto-generated transcript docs
        transcript_params = {
            "q": " and ".join(
                [
                    "mimeType='application/vnd.google-apps.document'",
                    "(name contains 'Transcript' or name contains 'Meeting notes')",
                    "trashed=false",
                ]
                + ([f"'{target_folder}' in parents"] if target_folder else [])
            ),
            "fields": "files(id,name,mimeType,modifiedTime)",
            "pageSize": 50,
            "orderBy": "modifiedTime desc",
        }

        try:
            transcript_result = _run_gws(
                [
                    "drive",
                    "files",
                    "list",
                    "--params",
                    json.dumps(transcript_params),
                ],
                timeout=60,
            )
            transcript_files = transcript_result.get("files", [])
            logger.info(
                f"Found {len(recordings)} recording(s) and "
                f"{len(transcript_files)} transcript doc(s) in Drive"
            )
        except RuntimeError as e:
            logger.debug(f"Transcript search failed: {e}")

        if not files:
            logger.warning("No Google Meet recordings found in Drive")

        logger.info(f"Found {len(files)} Meet recording(s)")
        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download a Meet recording from Drive."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        # For video files, download binary content via alt=media
        result = _run_gws(
            [
                "drive",
                "files",
                "get",
                "--params",
                json.dumps({"fileId": file.id, "alt": "media"}),
            ],
            timeout=300,
        )

        # Write the content — result may be raw binary or a dict wrapper
        raw = result.get("raw", "") if isinstance(result, dict) else str(result)
        destination.write_text(raw, encoding="utf-8")
        logger.info(f"Downloaded {file.name} to {destination}")
        return destination

    def fetch_transcript(self, recording_name: str) -> Optional[str]:
        """Fetch the companion transcript for a Meet recording.

        Google Meet creates transcript docs with names that typically match
        the recording date/time. This method searches for the matching
        Google Doc and extracts its text content.
        """
        transcript_id = self._find_matching_transcript(recording_name)
        if not transcript_id:
            logger.info(f"No matching transcript found for: {recording_name}")
            return None

        # Fetch the Google Doc content via the Docs API
        try:
            result = _run_gws(
                [
                    "docs",
                    "documents",
                    "get",
                    "--params",
                    json.dumps({"documentId": transcript_id}),
                ],
                timeout=60,
            )
        except RuntimeError as e:
            logger.warning(f"Failed to fetch transcript doc {transcript_id}: {e}")
            return None

        # Extract text from the Docs API structural response
        body = result.get("body", {})
        text_parts: list[str] = []
        for element in body.get("content", []):
            paragraph = element.get("paragraph", {})
            for pe in paragraph.get("elements", []):
                text_run = pe.get("textRun", {})
                text = text_run.get("content", "")
                if text.strip():
                    text_parts.append(text)

        if not text_parts:
            logger.warning(f"Transcript doc {transcript_id} had no extractable text")
            return None

        return "".join(text_parts)

    def _find_matching_transcript(self, recording_name: str) -> Optional[str]:
        """Search Drive for a transcript doc that matches a recording name.

        Meet recordings are typically named like:
            "Meet Recording 2026-03-07T14:30:00"
        And transcripts are named like:
            "Meeting Transcript 2026-03-07" or "2026-03-07 - Transcript"

        This extracts the date portion and searches for matching transcript docs.
        """
        # Extract a date string from the recording name (YYYY-MM-DD pattern)
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", recording_name)
        date_str = date_match.group(0) if date_match else recording_name

        # Search for transcript docs matching the date
        search_query = " and ".join(
            [
                "mimeType='application/vnd.google-apps.document'",
                f"name contains '{date_str}'",
                "(name contains 'Transcript' or name contains 'transcript' "
                "or name contains 'Meeting notes')",
                "trashed=false",
            ]
        )
        if self.drive_folder_id:
            search_query += f" and '{self.drive_folder_id}' in parents"

        try:
            result = _run_gws(
                [
                    "drive",
                    "files",
                    "list",
                    "--params",
                    json.dumps(
                        {
                            "q": search_query,
                            "fields": "files(id,name,modifiedTime)",
                            "pageSize": 5,
                            "orderBy": "modifiedTime desc",
                        }
                    ),
                ],
                timeout=60,
            )
        except RuntimeError as e:
            logger.debug(f"Transcript search failed for '{date_str}': {e}")
            return None

        files = result.get("files", [])
        if not files:
            logger.debug(f"No transcript docs found matching '{date_str}'")
            return None

        # Return the most recently modified match
        best = files[0]
        logger.info(f"Matched transcript: {best.get('name')} for recording: {recording_name}")
        return best.get("id")
