"""Google Gemini provider implementation using the google-genai SDK."""

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo

load_dotenv()
logger = logging.getLogger(__name__)

# Capabilities inferred from model id patterns
_VISION_KEYWORDS = {"gemini-2", "gemini-3", "gemini-pro", "gemini-flash", "gemini-ultra"}
_AUDIO_KEYWORDS = {"gemini-2", "gemini-3", "gemini-flash"}


class GeminiProvider(BaseProvider):
    """Google Gemini API provider via google-genai SDK."""

    provider_name = "gemini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if not self.api_key and not self.credentials_path:
            raise ValueError(
                "Neither GEMINI_API_KEY nor GOOGLE_APPLICATION_CREDENTIALS is set"
            )

        try:
            from google import genai
            self._genai = genai

            if self.api_key:
                self.client = genai.Client(api_key=self.api_key)
            else:
                # Service account → use Vertex AI mode
                import json

                with open(self.credentials_path) as f:
                    sa_info = json.load(f)
                project = sa_info.get("project_id", "")
                location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

                self.client = genai.Client(
                    vertexai=True,
                    project=project,
                    location=location,
                )
        except ImportError:
            raise ImportError(
                "google-genai package not installed. "
                "Install with: pip install google-genai"
            )

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        from google.genai import types

        model = model or "gemini-2.5-flash"
        # Convert OpenAI-style messages to Gemini contents
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg["content"])],
            ))

        response = self.client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        um = getattr(response, "usage_metadata", None)
        self._last_usage = {
            "input_tokens": getattr(um, "prompt_token_count", 0) if um else 0,
            "output_tokens": getattr(um, "candidates_token_count", 0) if um else 0,
        }
        return response.text or ""

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        from google.genai import types

        model = model or "gemini-2.5-flash"
        response = self.client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
            ),
        )
        um = getattr(response, "usage_metadata", None)
        self._last_usage = {
            "input_tokens": getattr(um, "prompt_token_count", 0) if um else 0,
            "output_tokens": getattr(um, "candidates_token_count", 0) if um else 0,
        }
        return response.text or ""

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        from google.genai import types

        model = model or "gemini-2.5-flash"
        audio_path = Path(audio_path)

        # Determine mime type
        suffix = audio_path.suffix.lower()
        mime_map = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
            ".webm": "audio/webm",
        }
        mime_type = mime_map.get(suffix, "audio/wav")

        # Read audio bytes
        audio_bytes = audio_path.read_bytes()

        lang_hint = f" The audio is in {language}." if language else ""
        prompt = (
            f"Transcribe this audio accurately.{lang_hint} "
            "Return a JSON object with keys: "
            '"text" (full transcript), '
            '"segments" (array of {start, end, text} objects with timestamps in seconds).'
        )

        response = self.client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=8192,
                response_mime_type="application/json",
            ),
        )

        # Parse JSON response
        import json
        try:
            data = json.loads(response.text)
        except (json.JSONDecodeError, TypeError):
            data = {"text": response.text or "", "segments": []}

        return {
            "text": data.get("text", ""),
            "segments": data.get("segments", []),
            "language": language,
            "duration": None,
            "provider": "gemini",
            "model": model,
        }

    def list_models(self) -> list[ModelInfo]:
        models = []
        try:
            for m in self.client.models.list():
                mid = m.name or ""
                # Strip prefix variants from different API modes
                for prefix in ("models/", "publishers/google/models/"):
                    if mid.startswith(prefix):
                        mid = mid[len(prefix):]
                        break
                display = getattr(m, "display_name", mid) or mid

                caps = []
                mid_lower = mid.lower()
                if "gemini" in mid_lower:
                    caps.append("chat")
                if any(kw in mid_lower for kw in _VISION_KEYWORDS):
                    caps.append("vision")
                if any(kw in mid_lower for kw in _AUDIO_KEYWORDS):
                    caps.append("audio")
                if "embedding" in mid_lower:
                    caps.append("embedding")

                if caps:
                    models.append(ModelInfo(
                        id=mid,
                        provider="gemini",
                        display_name=display,
                        capabilities=caps,
                    ))
        except Exception as e:
            logger.warning(f"Failed to list Gemini models: {e}")
        return sorted(models, key=lambda m: m.id)
