"""Local Whisper transcription provider — runs on-device with GPU acceleration."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Model size → approximate VRAM/RAM usage
_MODEL_SIZES = {
    "tiny": "~1GB",
    "base": "~1GB",
    "small": "~2GB",
    "medium": "~5GB",
    "large": "~10GB",
    "turbo": "~6GB",
}


class WhisperLocal:
    """
    Local Whisper transcription using openai-whisper.

    Uses MPS (Apple Silicon) or CUDA when available, falls back to CPU.
    No file size limits — processes audio directly on device.
    """

    def __init__(self, model_size: str = "large", device: Optional[str] = None):
        """
        Initialize local Whisper.

        Parameters
        ----------
        model_size : str
            Whisper model size: tiny, base, small, medium, large, turbo
        device : str, optional
            Force device: 'mps', 'cuda', 'cpu'. Auto-detects if None.
        """
        self.model_size = model_size
        self._model = None

        if device:
            self.device = device
        else:
            self.device = self._detect_device()

        logger.info(
            f"WhisperLocal: model={model_size} ({_MODEL_SIZES.get(model_size, '?')}), "
            f"device={self.device}"
        )

    @staticmethod
    def _detect_device() -> str:
        """Auto-detect the best available device."""
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            if torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    def _load_model(self):
        """Lazy-load the Whisper model."""
        if self._model is not None:
            return

        try:
            import whisper
        except ImportError:
            raise ImportError(
                "openai-whisper not installed. Run: pip install openai-whisper torch"
            )

        logger.info(f"Loading Whisper {self.model_size} model on {self.device}...")
        self._model = whisper.load_model(self.model_size, device=self.device)
        logger.info("Whisper model loaded")

    def transcribe(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
    ) -> dict:
        """
        Transcribe audio using local Whisper.

        No file size limits. Runs entirely on device.

        Returns dict compatible with ProviderManager transcription format.
        """
        self._load_model()
        audio_path = Path(audio_path)

        logger.info(f"Transcribing {audio_path.name} with Whisper {self.model_size}...")

        # fp16 only works reliably on CUDA; MPS produces NaN with large models
        kwargs = {"fp16": self.device == "cuda"}
        if language:
            kwargs["language"] = language

        result = self._model.transcribe(str(audio_path), **kwargs)

        segments = [
            {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            }
            for seg in result.get("segments", [])
        ]

        duration = segments[-1]["end"] if segments else None

        return {
            "text": result.get("text", "").strip(),
            "segments": segments,
            "language": result.get("language", language),
            "duration": duration,
            "provider": "whisper-local",
            "model": f"whisper-{self.model_size}",
        }

    @staticmethod
    def is_available() -> bool:
        """Check if local Whisper is installed and usable."""
        try:
            import whisper
            import torch
            return True
        except ImportError:
            return False
