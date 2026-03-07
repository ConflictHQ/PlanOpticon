"""Microsoft Teams meeting recording source using the m365 CLI.

Fetches Teams meeting recordings and transcripts via the Microsoft Graph API
through the `m365` CLI tool.

Requires: npm install -g @pnp/cli-microsoft365
Auth:     m365 login (interactive)
Docs:     https://pnp.github.io/cli-microsoft365/
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile
from video_processor.sources.m365_source import _run_m365

logger = logging.getLogger(__name__)


def _vtt_to_text(vtt: str) -> str:
    """Strip VTT timing metadata and return plain text.

    Removes WEBVTT headers, timestamps (00:00:00.000 --> 00:00:05.000),
    cue identifiers, and deduplicates consecutive identical lines.
    """
    lines = vtt.splitlines()
    text_lines: list[str] = []
    prev_line = ""

    for line in lines:
        stripped = line.strip()
        # Skip WEBVTT header and NOTE blocks
        if stripped.startswith("WEBVTT") or stripped.startswith("NOTE"):
            continue
        # Skip timestamp lines (e.g. 00:00:01.000 --> 00:00:05.000)
        if re.match(r"\d{2}:\d{2}[:\.][\d.]+ --> \d{2}:\d{2}[:\.][\d.]+", stripped):
            continue
        # Skip numeric cue identifiers
        if re.match(r"^\d+$", stripped):
            continue
        # Skip blank lines
        if not stripped:
            continue
        # Strip inline VTT tags like <v Speaker>
        cleaned = re.sub(r"<[^>]+>", "", stripped).strip()
        if cleaned and cleaned != prev_line:
            text_lines.append(cleaned)
            prev_line = cleaned

    return "\n".join(text_lines)


class TeamsRecordingSource(BaseSource):
    """
    Fetch Teams meeting recordings and transcripts via the m365 CLI / Graph API.

    Usage:
        source = TeamsRecordingSource(user_id="me")
        source.authenticate()
        recordings = source.list_videos()
        source.download_all(recordings, Path("./recordings"))

        # Fetch transcript for a specific meeting
        transcript = source.fetch_transcript(meeting_id)
    """

    def __init__(self, user_id: str = "me"):
        self.user_id = user_id

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
        """List Teams meeting recordings available for the user.

        Tries multiple approaches:
        1. Graph API onlineMeetings endpoint
        2. m365 teams meeting list command
        3. Fallback: search chat messages for recording links
        """
        files: List[SourceFile] = []

        # Approach 1: Graph API — list online meetings
        try:
            result = _run_m365(
                [
                    "request",
                    "--url",
                    f"https://graph.microsoft.com/v1.0/{self.user_id}/onlineMeetings",
                    "--method",
                    "get",
                ],
                timeout=60,
            )
            meetings = self._extract_meetings_list(result)
            for meeting in meetings:
                recording_files = self._get_meeting_recordings(meeting)
                files.extend(recording_files)

            if files:
                logger.info(f"Found {len(files)} recording(s) via Graph API onlineMeetings")
                return files
        except RuntimeError as e:
            logger.debug(f"onlineMeetings endpoint failed: {e}")

        # Approach 2: m365 teams meeting list
        try:
            result = _run_m365(["teams", "meeting", "list"], timeout=60)
            meetings = result if isinstance(result, list) else []
            for meeting in meetings:
                recording_files = self._get_meeting_recordings(meeting)
                files.extend(recording_files)

            if files:
                logger.info(f"Found {len(files)} recording(s) via m365 teams meeting list")
                return files
        except RuntimeError as e:
            logger.debug(f"teams meeting list failed: {e}")

        # Approach 3: Fallback — search chat messages for recording links
        try:
            result = _run_m365(
                [
                    "request",
                    "--url",
                    (
                        f"https://graph.microsoft.com/v1.0/{self.user_id}/chats"
                        "?$expand=messages($top=50)"
                        "&$filter=chatType eq 'meeting'"
                        "&$top=25"
                    ),
                    "--method",
                    "get",
                ],
                timeout=60,
            )
            chats = self._extract_value_list(result)
            for chat in chats:
                messages = chat.get("messages", [])
                for msg in messages:
                    body = msg.get("body", {}).get("content", "")
                    if "recording" in body.lower() or ".mp4" in body.lower():
                        topic = chat.get("topic", "Meeting Recording")
                        chat_id = chat.get("id", "")
                        msg_id = msg.get("id", "")
                        files.append(
                            SourceFile(
                                name=f"{topic}.mp4",
                                id=f"{chat_id}:{msg_id}",
                                mime_type="video/mp4",
                                modified_at=msg.get("createdDateTime"),
                            )
                        )
            if files:
                logger.info(f"Found {len(files)} recording link(s) in meeting chats")
        except RuntimeError as e:
            logger.debug(f"Chat message fallback failed: {e}")

        if not files:
            logger.warning("No Teams meeting recordings found")

        return files

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download a recording via its Graph API download URL."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        download_url = file.path
        if download_url:
            # Use the direct download URL from contentUrl / @microsoft.graph.downloadUrl
            _run_m365(
                [
                    "request",
                    "--url",
                    download_url,
                    "--method",
                    "get",
                    "--filePath",
                    str(destination),
                ],
                timeout=300,
            )
        else:
            # Try to get download URL from the recording ID
            meeting_id, _, recording_id = file.id.partition(":")
            if recording_id:
                url = (
                    f"https://graph.microsoft.com/v1.0/{self.user_id}"
                    f"/onlineMeetings/{meeting_id}"
                    f"/recordings/{recording_id}/content"
                )
            else:
                url = (
                    f"https://graph.microsoft.com/v1.0/{self.user_id}"
                    f"/onlineMeetings/{meeting_id}/recordings"
                )
                # Fetch recording list to find the content URL
                result = _run_m365(
                    ["request", "--url", url, "--method", "get"],
                    timeout=60,
                )
                recordings = self._extract_value_list(result)
                if recordings:
                    url = (
                        f"https://graph.microsoft.com/v1.0/{self.user_id}"
                        f"/onlineMeetings/{meeting_id}"
                        f"/recordings/{recordings[0].get('id', '')}/content"
                    )

            _run_m365(
                [
                    "request",
                    "--url",
                    url,
                    "--method",
                    "get",
                    "--filePath",
                    str(destination),
                ],
                timeout=300,
            )

        logger.info(f"Downloaded {file.name} to {destination}")
        return destination

    def fetch_transcript(self, meeting_id: str) -> Optional[str]:
        """Fetch the transcript for a Teams meeting.

        Queries the Graph API transcripts endpoint, downloads the transcript
        content, and converts VTT format to plain text.
        """
        try:
            result = _run_m365(
                [
                    "request",
                    "--url",
                    (
                        f"https://graph.microsoft.com/v1.0/{self.user_id}"
                        f"/onlineMeetings/{meeting_id}/transcripts"
                    ),
                    "--method",
                    "get",
                ],
                timeout=60,
            )
        except RuntimeError as e:
            logger.warning(f"Failed to list transcripts for meeting {meeting_id}: {e}")
            return None

        transcripts = self._extract_value_list(result)
        if not transcripts:
            logger.info(f"No transcripts found for meeting {meeting_id}")
            return None

        # Download the first available transcript
        transcript_id = transcripts[0].get("id", "")
        try:
            content_result = _run_m365(
                [
                    "request",
                    "--url",
                    (
                        f"https://graph.microsoft.com/v1.0/{self.user_id}"
                        f"/onlineMeetings/{meeting_id}"
                        f"/transcripts/{transcript_id}/content"
                    ),
                    "--method",
                    "get",
                    "--accept",
                    "text/vtt",
                ],
                timeout=60,
            )
        except RuntimeError as e:
            logger.warning(f"Failed to download transcript {transcript_id}: {e}")
            return None

        # content_result may be raw VTT text or a dict with raw key
        if isinstance(content_result, dict):
            raw = content_result.get("raw", "")
        else:
            raw = str(content_result)

        if not raw:
            logger.warning(f"Empty transcript content for meeting {meeting_id}")
            return None

        return _vtt_to_text(raw)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_meetings_list(self, result) -> list:
        """Extract meetings list from Graph API response."""
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("value", [])
        return []

    def _extract_value_list(self, result) -> list:
        """Extract value list from a Graph API response."""
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("value", [])
        return []

    def _get_meeting_recordings(self, meeting: dict) -> List[SourceFile]:
        """Fetch recordings for a single meeting and return SourceFile entries."""
        meeting_id = meeting.get("id", "")
        subject = meeting.get("subject", meeting.get("topic", "Teams Meeting"))
        start_time = meeting.get("startDateTime", meeting.get("createdDateTime"))

        if not meeting_id:
            return []

        try:
            result = _run_m365(
                [
                    "request",
                    "--url",
                    (
                        f"https://graph.microsoft.com/v1.0/{self.user_id}"
                        f"/onlineMeetings/{meeting_id}/recordings"
                    ),
                    "--method",
                    "get",
                ],
                timeout=60,
            )
        except RuntimeError:
            return []

        recordings = self._extract_value_list(result)
        files: List[SourceFile] = []
        for rec in recordings:
            rec_id = rec.get("id", "")
            download_url = rec.get("content.downloadUrl", rec.get("contentUrl"))
            files.append(
                SourceFile(
                    name=f"{subject}.mp4",
                    id=f"{meeting_id}:{rec_id}",
                    mime_type="video/mp4",
                    modified_at=start_time,
                    path=download_url,
                )
            )

        return files
