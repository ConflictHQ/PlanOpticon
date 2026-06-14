"""Deepgram provider — fast pre-recorded transcription with speaker diarization.

Transcription-only provider (no chat/vision). Uses Deepgram's pre-recorded
`/v1/listen` endpoint with `diarize=true` + `utterances=true`, which returns
speaker-labeled utterances we map straight onto TranscriptSegment.speaker.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo, ProviderRegistry

load_dotenv()
logger = logging.getLogger(__name__)

_LISTEN_URL = "https://api.deepgram.com/v1/listen"
_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
}


class DeepgramProvider(BaseProvider):
    """Deepgram speech-to-text provider (transcription + diarization only)."""

    provider_name = "deepgram"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY not set")

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
        diarize: bool = False,
        speaker_hints: Optional[list[str]] = None,
    ) -> dict:
        model = model or "nova-3"
        audio_path = Path(audio_path)
        params = {
            "model": model,
            "smart_format": "true",
            "punctuate": "true",
            "diarize": "true" if diarize else "false",
            "utterances": "true",
        }
        if language:
            params["language"] = language
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": _MIME.get(audio_path.suffix.lower(), "application/octet-stream"),
        }
        logger.info(f"Deepgram transcribing {audio_path.name} (model={model}, diarize={diarize})")
        resp = requests.post(
            _LISTEN_URL,
            params=params,
            headers=headers,
            data=audio_path.read_bytes(),
            timeout=900,
        )
        resp.raise_for_status()
        payload = resp.json()

        results = payload.get("results", {})
        channels = results.get("channels") or [{}]
        alt = (channels[0].get("alternatives") or [{}])[0]
        full_text = alt.get("transcript", "")

        segments = []
        for utt in results.get("utterances") or []:
            text = (utt.get("transcript") or "").strip()
            if not text:
                continue
            seg = {"start": utt.get("start", 0.0), "end": utt.get("end", 0.0), "text": text}
            if diarize and "speaker" in utt:
                seg["speaker"] = f"Speaker {utt['speaker']}"
            segments.append(seg)

        if not full_text and segments:
            full_text = " ".join(s["text"] for s in segments)

        return {
            "text": full_text,
            "segments": segments,
            "language": (channels[0].get("detected_language") or language),
            "duration": payload.get("metadata", {}).get("duration"),
            "provider": "deepgram",
            "model": model,
        }

    def chat(self, messages, max_tokens=4096, temperature=0.7, model=None) -> str:
        raise NotImplementedError("Deepgram is a transcription-only provider")

    def analyze_image(self, image_bytes, prompt, max_tokens=4096, model=None) -> str:
        raise NotImplementedError("Deepgram is a transcription-only provider")

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id=mid, provider="deepgram", display_name=mid, capabilities=["audio"])
            for mid in ("nova-3", "nova-2")
        ]


ProviderRegistry.register(
    name="deepgram",
    provider_class=DeepgramProvider,
    env_var="DEEPGRAM_API_KEY",
    model_prefixes=["nova-", "deepgram"],
    default_models={"audio": "nova-3"},
)
