"""ElevenLabs provider — high-accuracy transcription (Scribe) with diarization.

Transcription-only provider (no chat/vision). Uses the ElevenLabs
`/v1/speech-to-text` endpoint (model `scribe_v1`) with word-level timestamps and
`diarize=true`. Words carry a `speaker_id`; we group consecutive same-speaker
words into TranscriptSegments.
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

_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
}


def _fmt_speaker(speaker_id: Optional[str]) -> Optional[str]:
    """Normalize 'speaker_0' -> 'Speaker 0'; pass anything else through."""
    if not speaker_id:
        return None
    tail = str(speaker_id).rsplit("_", 1)[-1]
    return f"Speaker {tail}" if tail.isdigit() else str(speaker_id)


class ElevenLabsProvider(BaseProvider):
    """ElevenLabs Scribe speech-to-text provider (transcription + diarization only)."""

    provider_name = "elevenlabs"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY not set")

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
        diarize: bool = False,
        speaker_hints: Optional[list[str]] = None,
    ) -> dict:
        model = model or "scribe_v1"
        audio_path = Path(audio_path)
        mime = _MIME.get(audio_path.suffix.lower(), "application/octet-stream")
        data = {
            "model_id": model,
            "diarize": "true" if diarize else "false",
            "timestamps_granularity": "word",
        }
        if language:
            data["language_code"] = language
        logger.info(f"ElevenLabs transcribing {audio_path.name} (model={model}, diarize={diarize})")
        resp = requests.post(
            _STT_URL,
            headers={"xi-api-key": self.api_key},
            files={"file": (audio_path.name, audio_path.read_bytes(), mime)},
            data=data,
            timeout=900,
        )
        resp.raise_for_status()
        payload = resp.json()

        full_text = (payload.get("text") or "").strip()

        # Group consecutive words into turns; start a new turn when the speaker
        # changes (diarized) — spacing tokens attach to the current turn's text.
        groups: list[dict] = []
        cur = None
        for w in payload.get("words") or []:
            if w.get("type") == "spacing":
                if cur is not None:
                    cur["text"] += w.get("text", "")
                continue
            spk = w.get("speaker_id")
            if cur is None or (diarize and spk != cur["_spk"]):
                cur = {
                    "_spk": spk,
                    "start": w.get("start", 0.0),
                    "end": w.get("end", 0.0),
                    "text": w.get("text", ""),
                }
                groups.append(cur)
            else:
                cur["text"] += w.get("text", "")
                cur["end"] = w.get("end", cur["end"])

        segments = []
        for g in groups:
            seg = {"start": g["start"], "end": g["end"], "text": g["text"].strip()}
            spk = _fmt_speaker(g["_spk"])
            if diarize and spk:
                seg["speaker"] = spk
            segments.append(seg)

        if not full_text and segments:
            full_text = " ".join(s["text"] for s in segments)

        return {
            "text": full_text,
            "segments": segments,
            "language": payload.get("language_code", language),
            "duration": (segments[-1]["end"] if segments else None),
            "provider": "elevenlabs",
            "model": model,
        }

    def chat(self, messages, max_tokens=4096, temperature=0.7, model=None) -> str:
        raise NotImplementedError("ElevenLabs is a transcription-only provider")

    def analyze_image(self, image_bytes, prompt, max_tokens=4096, model=None) -> str:
        raise NotImplementedError("ElevenLabs is a transcription-only provider")

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="scribe_v1",
                provider="elevenlabs",
                display_name="scribe_v1",
                capabilities=["audio"],
            )
        ]


ProviderRegistry.register(
    name="elevenlabs",
    provider_class=ElevenLabsProvider,
    env_var="ELEVENLABS_API_KEY",
    model_prefixes=["scribe"],
    default_models={"audio": "scribe_v1"},
)
