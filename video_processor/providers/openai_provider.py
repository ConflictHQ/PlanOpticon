"""OpenAI provider implementation."""

import base64
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from video_processor.providers.base import BaseProvider, ModelInfo

load_dotenv()
logger = logging.getLogger(__name__)

# Models known to have vision capability
_VISION_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o1", "o3", "o3-mini", "o4-mini"}
_AUDIO_MODELS = {"whisper-1"}


class OpenAIProvider(BaseProvider):
    """OpenAI API provider."""

    provider_name = "openai"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=self.api_key)

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = model or "gpt-4o"
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self._last_usage = {
            "input_tokens": getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
            "output_tokens": getattr(response.usage, "completion_tokens", 0) if response.usage else 0,
        }
        return response.choices[0].message.content or ""

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        model = model or "gpt-4o"
        b64 = base64.b64encode(image_bytes).decode()
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
            max_tokens=max_tokens,
        )
        self._last_usage = {
            "input_tokens": getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
            "output_tokens": getattr(response.usage, "completion_tokens", 0) if response.usage else 0,
        }
        return response.choices[0].message.content or ""

    # Whisper API limit is 25MB
    _MAX_FILE_SIZE = 25 * 1024 * 1024

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        model = model or "whisper-1"
        audio_path = Path(audio_path)
        file_size = audio_path.stat().st_size

        if file_size <= self._MAX_FILE_SIZE:
            return self._transcribe_single(audio_path, language, model)

        # File too large — split into chunks and transcribe each
        logger.info(
            f"Audio file {file_size / 1024 / 1024:.1f}MB exceeds Whisper 25MB limit, chunking..."
        )
        return self._transcribe_chunked(audio_path, language, model)

    def _transcribe_single(
        self, audio_path: Path, language: Optional[str], model: str
    ) -> dict:
        """Transcribe a single audio file."""
        with open(audio_path, "rb") as f:
            kwargs = {"model": model, "file": f}
            if language:
                kwargs["language"] = language
            response = self.client.audio.transcriptions.create(
                **kwargs, response_format="verbose_json"
            )
        return {
            "text": response.text,
            "segments": [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                }
                for seg in (response.segments or [])
            ],
            "language": getattr(response, "language", language),
            "duration": getattr(response, "duration", None),
            "provider": "openai",
            "model": model,
        }

    def _transcribe_chunked(
        self, audio_path: Path, language: Optional[str], model: str
    ) -> dict:
        """Split audio into chunks under 25MB and transcribe each."""
        import tempfile
        from video_processor.extractors.audio_extractor import AudioExtractor

        extractor = AudioExtractor()
        audio_data, sr = extractor.load_audio(audio_path)
        total_duration = len(audio_data) / sr

        # Calculate chunk duration to stay under 25MB
        # WAV: 16-bit mono = 2 bytes/sample, plus header overhead
        bytes_per_second = sr * 2
        max_seconds = self._MAX_FILE_SIZE // bytes_per_second
        # Use 80% of max to leave headroom
        chunk_ms = int(max_seconds * 0.8 * 1000)

        segments_data = extractor.segment_audio(audio_data, sr, segment_length_ms=chunk_ms)
        logger.info(f"Split into {len(segments_data)} chunks of ~{chunk_ms / 1000:.0f}s each")

        all_text = []
        all_segments = []
        time_offset = 0.0
        detected_language = language

        with tempfile.TemporaryDirectory() as tmpdir:
            for i, chunk in enumerate(segments_data):
                chunk_path = Path(tmpdir) / f"chunk_{i:03d}.wav"
                extractor.save_segment(chunk, chunk_path, sr)

                logger.info(f"Transcribing chunk {i + 1}/{len(segments_data)}...")
                result = self._transcribe_single(chunk_path, language, model)

                all_text.append(result["text"])
                for seg in result.get("segments", []):
                    all_segments.append({
                        "start": seg["start"] + time_offset,
                        "end": seg["end"] + time_offset,
                        "text": seg["text"],
                    })

                if not detected_language and result.get("language"):
                    detected_language = result["language"]

                time_offset += len(chunk) / sr

        return {
            "text": " ".join(all_text),
            "segments": all_segments,
            "language": detected_language,
            "duration": total_duration,
            "provider": "openai",
            "model": model,
        }

    def list_models(self) -> list[ModelInfo]:
        models = []
        try:
            for m in self.client.models.list():
                mid = m.id
                caps = []
                # Infer capabilities from model id
                if any(mid.startswith(p) for p in ("gpt-", "o1", "o3", "o4")):
                    caps.append("chat")
                if any(v in mid for v in _VISION_MODELS) or "gpt-4o" in mid or "gpt-4.1" in mid:
                    caps.append("vision")
                if mid in _AUDIO_MODELS or mid.startswith("whisper"):
                    caps.append("audio")
                if "embedding" in mid:
                    caps.append("embedding")
                if caps:
                    models.append(ModelInfo(
                        id=mid,
                        provider="openai",
                        display_name=mid,
                        capabilities=caps,
                    ))
        except Exception as e:
            logger.warning(f"Failed to list OpenAI models: {e}")
        return sorted(models, key=lambda m: m.id)
