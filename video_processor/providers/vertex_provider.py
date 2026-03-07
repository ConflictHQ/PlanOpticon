"""Google Vertex AI provider implementation."""

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo, ProviderRegistry

load_dotenv()
logger = logging.getLogger(__name__)

# Curated list of models available on Vertex AI
_VERTEX_MODELS = [
    ModelInfo(
        id="gemini-2.0-flash",
        provider="vertex",
        display_name="Gemini 2.0 Flash",
        capabilities=["chat", "vision", "audio"],
    ),
    ModelInfo(
        id="gemini-2.0-pro",
        provider="vertex",
        display_name="Gemini 2.0 Pro",
        capabilities=["chat", "vision", "audio"],
    ),
    ModelInfo(
        id="gemini-1.5-pro",
        provider="vertex",
        display_name="Gemini 1.5 Pro",
        capabilities=["chat", "vision", "audio"],
    ),
    ModelInfo(
        id="gemini-1.5-flash",
        provider="vertex",
        display_name="Gemini 1.5 Flash",
        capabilities=["chat", "vision", "audio"],
    ),
]


class VertexProvider(BaseProvider):
    """Google Vertex AI provider using google-genai SDK with Vertex config."""

    provider_name = "vertex"

    def __init__(
        self,
        project: Optional[str] = None,
        location: Optional[str] = None,
    ):
        try:
            from google import genai
            from google.genai import types  # noqa: F401
        except ImportError:
            raise ImportError(
                "google-cloud-aiplatform or google-genai package not installed. "
                "Install with: pip install google-cloud-aiplatform"
            )

        self._genai = genai
        self._project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        self._location = location or os.getenv("GOOGLE_CLOUD_REGION", "us-central1")

        if not self._project:
            raise ValueError("GOOGLE_CLOUD_PROJECT not set")

        self.client = genai.Client(
            vertexai=True,
            project=self._project,
            location=self._location,
        )
        self._last_usage = {}

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        from google.genai import types

        model = model or "gemini-2.0-flash"
        if model.startswith("vertex/"):
            model = model[len("vertex/") :]

        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg["content"])],
                )
            )

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

        model = model or "gemini-2.0-flash"
        if model.startswith("vertex/"):
            model = model[len("vertex/") :]

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
        import json

        from google.genai import types

        model = model or "gemini-2.0-flash"
        if model.startswith("vertex/"):
            model = model[len("vertex/") :]

        audio_path = Path(audio_path)
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

        try:
            data = json.loads(response.text)
        except (json.JSONDecodeError, TypeError):
            data = {"text": response.text or "", "segments": []}

        um = getattr(response, "usage_metadata", None)
        self._last_usage = {
            "input_tokens": getattr(um, "prompt_token_count", 0) if um else 0,
            "output_tokens": getattr(um, "candidates_token_count", 0) if um else 0,
        }

        return {
            "text": data.get("text", ""),
            "segments": data.get("segments", []),
            "language": language,
            "duration": None,
            "provider": "vertex",
            "model": model,
        }

    def list_models(self) -> list[ModelInfo]:
        return list(_VERTEX_MODELS)


ProviderRegistry.register(
    name="vertex",
    provider_class=VertexProvider,
    env_var="GOOGLE_CLOUD_PROJECT",
    model_prefixes=["vertex/"],
    default_models={
        "chat": "gemini-2.0-flash",
        "vision": "gemini-2.0-flash",
        "audio": "gemini-2.0-flash",
    },
)
