"""Tests for the concrete OpenAIProvider (chat, vision, transcription, listing).

The base OpenAICompatibleProvider is covered in test_providers.py; this file
exercises video_processor.providers.openai_provider.OpenAIProvider, mocking only
the OpenAI SDK entrypoint so the real request/response mapping runs.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from video_processor.providers.openai_provider import OpenAIProvider


def _make_client(mock_cls):
    client = MagicMock()
    mock_cls.return_value = client
    return client


def _chat_response(text, prompt_tokens=5, completion_tokens=10):
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = text
    resp.choices = [choice]
    resp.usage.prompt_tokens = prompt_tokens
    resp.usage.completion_tokens = completion_tokens
    return resp


class TestConstruction:
    def test_missing_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY not set"):
                OpenAIProvider(api_key=None)

    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_explicit_key_builds_client(self, mock_cls):
        client = _make_client(mock_cls)
        provider = OpenAIProvider(api_key="sk-test")
        assert provider.api_key == "sk-test"
        assert provider.client is client
        mock_cls.assert_called_once_with(api_key="sk-test")

    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_key_from_env(self, mock_cls):
        _make_client(mock_cls)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env"}, clear=True):
            provider = OpenAIProvider()
        assert provider.api_key == "sk-env"


class TestChat:
    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_chat_returns_text_and_records_usage(self, mock_cls):
        client = _make_client(mock_cls)
        client.chat.completions.create.return_value = _chat_response("hello back", 5, 12)

        provider = OpenAIProvider(api_key="sk-test")
        out = provider.chat([{"role": "user", "content": "hi"}])

        assert out == "hello back"
        assert provider._last_usage == {"input_tokens": 5, "output_tokens": 12}
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "gpt-4o-mini"  # default
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]

    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_chat_honours_explicit_model_and_params(self, mock_cls):
        client = _make_client(mock_cls)
        client.chat.completions.create.return_value = _chat_response("x")

        provider = OpenAIProvider(api_key="sk-test")
        provider.chat(
            [{"role": "user", "content": "hi"}],
            max_tokens=256,
            temperature=0.1,
            model="gpt-4.1",
        )
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "gpt-4.1"
        assert kwargs["max_tokens"] == 256
        assert kwargs["temperature"] == 0.1

    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_chat_none_content_returns_empty_string(self, mock_cls):
        client = _make_client(mock_cls)
        client.chat.completions.create.return_value = _chat_response(None)

        provider = OpenAIProvider(api_key="sk-test")
        assert provider.chat([{"role": "user", "content": "hi"}]) == ""

    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_chat_missing_usage_defaults_to_zero(self, mock_cls):
        client = _make_client(mock_cls)
        resp = _chat_response("ok")
        resp.usage = None
        client.chat.completions.create.return_value = resp

        provider = OpenAIProvider(api_key="sk-test")
        provider.chat([{"role": "user", "content": "hi"}])
        assert provider._last_usage == {"input_tokens": 0, "output_tokens": 0}


class TestAnalyzeImage:
    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_analyze_image_encodes_and_returns_text(self, mock_cls):
        client = _make_client(mock_cls)
        client.chat.completions.create.return_value = _chat_response("a cat", 100, 5)

        provider = OpenAIProvider(api_key="sk-test")
        out = provider.analyze_image(b"\x89PNGdata", "what is this?", model="gpt-4o")

        assert out == "a cat"
        assert provider._last_usage["input_tokens"] == 100
        # The image is passed as a base64 data URL inside the content parts.
        content = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        image_part = [p for p in content if p["type"] == "image_url"][0]
        assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


class TestTranscribe:
    def _verbose_response(self, text="hello world"):
        seg = MagicMock()
        seg.start = 0.0
        seg.end = 1.5
        seg.text = "hello world"
        resp = MagicMock()
        resp.text = text
        resp.segments = [seg]
        resp.language = "en"
        resp.duration = 1.5
        return resp

    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_transcribe_single_small_file(self, mock_cls, tmp_path):
        client = _make_client(mock_cls)
        client.audio.transcriptions.create.return_value = self._verbose_response()

        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"\x00\x01\x02\x03")

        provider = OpenAIProvider(api_key="sk-test")
        result = provider.transcribe_audio(audio, language="en")

        assert result["text"] == "hello world"
        assert result["provider"] == "openai"
        assert result["model"] == "whisper-1"
        assert result["segments"] == [{"start": 0.0, "end": 1.5, "text": "hello world"}]
        # language kwarg was forwarded to the SDK
        assert client.audio.transcriptions.create.call_args.kwargs["language"] == "en"

    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_transcribe_forwards_prompt(self, mock_cls, tmp_path):
        client = _make_client(mock_cls)
        client.audio.transcriptions.create.return_value = self._verbose_response()

        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"\x00")

        provider = OpenAIProvider(api_key="sk-test")
        provider.transcribe_audio(audio, prompt="Speakers: Alice, Bob.")
        assert (
            client.audio.transcriptions.create.call_args.kwargs["prompt"] == "Speakers: Alice, Bob."
        )

    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_transcribe_large_file_chunks(self, mock_cls, tmp_path):
        """A file over the 25MB limit is split and each chunk transcribed,
        with segment timestamps offset by the running chunk duration."""
        _make_client(mock_cls)

        audio = tmp_path / "big.wav"
        audio.write_bytes(b"\x00" * 100)

        provider = OpenAIProvider(api_key="sk-test")
        provider._MAX_FILE_SIZE = 10  # force the chunked path

        fake_extractor = MagicMock()
        sr = 16000
        fake_extractor.load_audio.return_value = ([0] * (sr * 2), sr)  # 2.0s total
        fake_extractor.segment_audio.return_value = [[0] * sr, [0] * sr]  # two 1s chunks

        per_chunk = [
            {
                "text": "first",
                "segments": [{"start": 0.0, "end": 1.0, "text": "first"}],
                "language": "en",
            },
            {
                "text": "second",
                "segments": [{"start": 0.0, "end": 1.0, "text": "second"}],
                "language": None,
            },
        ]

        with patch(
            "video_processor.extractors.audio_extractor.AudioExtractor",
            return_value=fake_extractor,
        ):
            with patch.object(OpenAIProvider, "_transcribe_single", side_effect=per_chunk):
                result = provider.transcribe_audio(audio)

        assert result["text"] == "first second"
        assert result["language"] == "en"
        assert result["duration"] == 2.0
        # Second chunk's segment is shifted by the 1.0s first-chunk offset.
        assert result["segments"][0] == {"start": 0.0, "end": 1.0, "text": "first"}
        assert result["segments"][1] == {"start": 1.0, "end": 2.0, "text": "second"}


class TestListModels:
    def _model(self, mid):
        m = MagicMock()
        m.id = mid
        return m

    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_list_models_infers_capabilities(self, mock_cls):
        client = _make_client(mock_cls)
        client.models.list.return_value = [
            self._model("gpt-4o"),
            self._model("whisper-1"),
            self._model("text-embedding-3-small"),
            self._model("o1"),
            self._model("dall-e-3"),  # no inferred caps -> excluded
        ]

        provider = OpenAIProvider(api_key="sk-test")
        models = provider.list_models()
        by_id = {m.id: m for m in models}

        assert "dall-e-3" not in by_id
        assert "vision" in by_id["gpt-4o"].capabilities
        assert "chat" in by_id["gpt-4o"].capabilities
        assert by_id["whisper-1"].capabilities == ["audio"]
        assert by_id["text-embedding-3-small"].capabilities == ["embedding"]
        # "o1" is itself listed in _VISION_MODELS, so the substring check tags it
        # vision as well as chat — assert the module's actual inference.
        assert by_id["o1"].capabilities == ["chat", "vision"]
        # sorted by id
        assert [m.id for m in models] == sorted(m.id for m in models)

    @patch("video_processor.providers.openai_provider.OpenAI")
    def test_list_models_handles_error(self, mock_cls):
        client = _make_client(mock_cls)
        client.models.list.side_effect = RuntimeError("boom")

        provider = OpenAIProvider(api_key="sk-test")
        assert provider.list_models() == []
