"""YouTube source connector using yt-dlp for video/audio download and caption extraction."""

import logging
import re
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)

_YT_URL_PATTERN = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]{11})"
)


def _extract_video_id(url: str) -> str:
    """Extract the 11-character video ID from a YouTube URL."""
    match = _YT_URL_PATTERN.search(url)
    if not match:
        raise ValueError(f"Could not extract YouTube video ID from: {url}")
    return match.group(1)


class YouTubeSource(BaseSource):
    """
    Download YouTube videos/audio and extract captions via yt-dlp.

    Requires: pip install yt-dlp
    """

    def __init__(self, url: str, audio_only: bool = False):
        self.url = url
        self.video_id = _extract_video_id(url)
        self.audio_only = audio_only

    def authenticate(self) -> bool:
        """No auth needed for public videos. Returns True if yt-dlp is available."""
        try:
            import yt_dlp  # noqa: F401

            return True
        except ImportError:
            logger.error("yt-dlp not installed. Run: pip install yt-dlp")
            return False

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """Return a single SourceFile representing the YouTube video."""
        import yt_dlp

        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(self.url, download=False)

        return [
            SourceFile(
                name=info.get("title", self.video_id),
                id=self.video_id,
                size_bytes=info.get("filesize"),
                mime_type="audio/webm" if self.audio_only else "video/mp4",
            )
        ]

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download the video or audio to destination path."""
        import yt_dlp

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        opts = {
            "outtmpl": str(destination),
            "quiet": True,
        }
        if self.audio_only:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
        else:
            opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([self.url])

        logger.info(f"Downloaded YouTube video {self.video_id} to {destination}")
        return destination

    def fetch_captions(self, lang: str = "en") -> Optional[str]:
        """Extract auto-generated or manual captions as plain text."""
        import yt_dlp

        opts = {
            "quiet": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": [lang],
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(self.url, download=False)

        subs = info.get("subtitles", {}).get(lang) or info.get("automatic_captions", {}).get(lang)
        if not subs:
            logger.warning(f"No captions found for language '{lang}'")
            return None

        # Prefer vtt/srv format for text extraction
        for fmt in subs:
            if fmt.get("ext") in ("vtt", "srv3", "json3"):
                import requests

                resp = requests.get(fmt["url"], timeout=30)
                return resp.text

        return None
