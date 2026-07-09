"""Replicate provider — hosted model zoo via the prediction API.

Uses Replicate's HTTP prediction API (https://api.replicate.com/v1) directly
with plain ``requests`` and a ``Prefer: wait`` header, so the core stays lean
(no ``replicate`` SDK dependency — same approach as the Deepgram/ElevenLabs
providers). One API fronts many models: language models for chat, LLaVA-style
models for vision, and Whisper variants for transcription.

Model routing: an incoming id may carry a ``replicate/`` prefix, which is
stripped before the API call. The remainder is ``owner/name`` (e.g.
``replicate/openai/whisper`` -> owner ``openai``, name ``whisper``).
"""

import base64
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from video_processor.providers.base import BaseProvider, ModelInfo, ProviderRegistry

load_dotenv()
logger = logging.getLogger(__name__)

_BASE_URL = "https://api.replicate.com/v1"
_PREFIX = "replicate/"
_TIMEOUT = 900
_POLL_INTERVAL = 2.0
_MAX_POLLS = 60  # bounded: ~2 minutes of polling after the initial wait window
_TERMINAL = {"succeeded", "failed", "canceled"}
_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
}


def _join_output(output) -> str:
    """Join a Replicate language-model output (list of string chunks) into text."""
    if isinstance(output, list):
        return "".join(str(chunk) for chunk in output)
    if output is None:
        return ""
    return str(output)


def _infer_capabilities(name: str, description: str) -> list[str]:
    """Best-effort capability inference from a model's name/description."""
    text = f"{name} {description}".lower()
    caps: list[str] = []
    if any(k in text for k in ("whisper", "transcri", "speech", "asr")):
        caps.append("audio")
    if any(k in text for k in ("llava", "vision", "caption", "clip", "blip")):
        caps.append("vision")
    if not caps:
        caps.append("chat")
    return caps


class ReplicateProvider(BaseProvider):
    """Replicate provider (chat, vision, transcription) via the prediction API."""

    provider_name = "replicate"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("REPLICATE_API_TOKEN")
        if not self.api_key:
            raise ValueError("REPLICATE_API_TOKEN not set")
        # Replicate bills per-second hardware time, not tokens, so there are no
        # token counts to report — recorded as zeros (usage.json shows the call
        # at $0 since there is no static token price for Replicate models).
        self._last_usage = {"input_tokens": 0, "output_tokens": 0}

    # --- internal helpers ---

    def _headers(self, prefer_wait: bool = False) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if prefer_wait:
            headers["Prefer"] = "wait"
        return headers

    @staticmethod
    def _strip_prefix(model: str) -> str:
        return model[len(_PREFIX) :] if model.startswith(_PREFIX) else model

    @staticmethod
    def _split_model(model: str) -> tuple[str, str]:
        owner, _, name = model.partition("/")
        return owner, name

    @staticmethod
    def _raise_if_failed(prediction: dict) -> None:
        status = prediction.get("status")
        if status in ("failed", "canceled"):
            detail = prediction.get("error") or status
            raise RuntimeError(f"Replicate prediction {status}: {detail}")

    def _poll(self, prediction: dict) -> dict:
        """Poll GET /predictions/{id} until the prediction reaches a terminal state."""
        status = prediction.get("status")
        pred_id = prediction.get("id")
        tries = 0
        while status not in _TERMINAL and tries < _MAX_POLLS:
            time.sleep(_POLL_INTERVAL)
            resp = requests.get(
                f"{_BASE_URL}/predictions/{pred_id}",
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            prediction = resp.json()
            status = prediction.get("status")
            tries += 1
        return prediction

    def _predict(self, model: str, model_input: dict, poll: bool = False) -> dict:
        """Create a prediction (blocking via Prefer: wait), optionally polling to completion."""
        owner, name = self._split_model(model)
        resp = requests.post(
            f"{_BASE_URL}/models/{owner}/{name}/predictions",
            headers=self._headers(prefer_wait=True),
            json={"input": model_input},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        prediction = resp.json()
        if poll:
            prediction = self._poll(prediction)
        self._raise_if_failed(prediction)
        return prediction

    # --- BaseProvider API ---

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        model = self._strip_prefix(model or "meta/meta-llama-3-8b-instruct")
        prompt = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") != "system")
        system_prompt = "\n".join(
            str(m.get("content", "")) for m in messages if m.get("role") == "system"
        )
        model_input = {"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}
        if system_prompt:
            model_input["system_prompt"] = system_prompt
        prediction = self._predict(model, model_input, poll=False)
        self._last_usage = {"input_tokens": 0, "output_tokens": 0}
        return _join_output(prediction.get("output"))

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        model = self._strip_prefix(model or "yorickvp/llava-13b")
        b64 = base64.b64encode(image_bytes).decode()
        model_input = {"image": f"data:image/jpeg;base64,{b64}", "prompt": prompt}
        prediction = self._predict(model, model_input, poll=False)
        self._last_usage = {"input_tokens": 0, "output_tokens": 0}
        return _join_output(prediction.get("output"))

    def transcribe_audio(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        model = self._strip_prefix(model or "openai/whisper")
        audio_path = Path(audio_path)
        mime = _MIME.get(audio_path.suffix.lower(), "application/octet-stream")
        b64 = base64.b64encode(audio_path.read_bytes()).decode()
        prediction = self._predict(model, {"audio": f"data:{mime};base64,{b64}"}, poll=True)
        self._last_usage = {"input_tokens": 0, "output_tokens": 0}

        output = prediction.get("output") or {}
        if isinstance(output, str):
            # Some ASR models return just the transcript string.
            text, raw_segments, detected, duration = output, [], None, None
        else:
            text = output.get("transcription") or output.get("text") or ""
            raw_segments = output.get("segments") or []
            detected = output.get("detected_language") or output.get("language")
            duration = output.get("duration")

        segments = []
        for seg in raw_segments:
            if not isinstance(seg, dict):
                continue
            segments.append(
                {
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                    "text": (seg.get("text") or "").strip(),
                }
            )
        if duration is None and segments:
            duration = segments[-1]["end"]

        return {
            "text": text.strip() if isinstance(text, str) else text,
            "segments": segments,
            "language": detected or language,
            "duration": duration,
            "provider": "replicate",
            "model": model,
        }

    def list_models(self) -> list[ModelInfo]:
        try:
            resp = requests.get(f"{_BASE_URL}/models", headers=self._headers(), timeout=_TIMEOUT)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as e:
            logger.warning(f"Failed to list Replicate models: {e}")
            return []

        models = []
        for m in results:
            owner = m.get("owner", "")
            name = m.get("name", "")
            if not owner or not name:
                continue
            mid = f"{owner}/{name}"
            models.append(
                ModelInfo(
                    id=mid,
                    provider="replicate",
                    display_name=mid,
                    capabilities=_infer_capabilities(name, m.get("description") or ""),
                )
            )
        return models


ProviderRegistry.register(
    name="replicate",
    provider_class=ReplicateProvider,
    env_var="REPLICATE_API_TOKEN",
    model_prefixes=["replicate/"],
    default_models={
        "chat": "meta/meta-llama-3-8b-instruct",
        "vision": "yorickvp/llava-13b",
        "audio": "openai/whisper",
    },
)
