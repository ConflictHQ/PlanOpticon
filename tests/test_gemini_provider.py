"""Tests for GeminiProvider (construction, chat, vision, transcription, listing).

google-genai is a core dependency, so the real `types` build the request; only
the genai.Client / provider.client boundary is mocked.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from video_processor.providers.gemini_provider import GeminiProvider


def _provider():
    provider = GeminiProvider(api_key="test-key")
    provider.client = MagicMock()
    return provider


def _content_response(text, prompt_tokens=11, candidates_tokens=22):
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata.prompt_token_count = prompt_tokens
    resp.usage_metadata.candidates_token_count = candidates_tokens
    return resp


class TestConstruction:
    def test_missing_key_and_creds_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Neither GEMINI_API_KEY"):
                GeminiProvider(api_key=None, credentials_path=None)

    @patch("google.genai.Client")
    def test_api_key_branch(self, mock_client):
        GeminiProvider(api_key="test-key")
        mock_client.assert_called_once_with(api_key="test-key")

    @patch("google.genai.Client")
    def test_service_account_uses_vertex(self, mock_client, tmp_path):
        creds = tmp_path / "sa.json"
        creds.write_text(json.dumps({"project_id": "my-proj"}))
        with patch.dict(os.environ, {"GOOGLE_CLOUD_LOCATION": "europe-west1"}, clear=True):
            GeminiProvider(api_key=None, credentials_path=str(creds))
        mock_client.assert_called_once_with(
            vertexai=True, project="my-proj", location="europe-west1"
        )


class TestChat:
    def test_chat_maps_messages_and_records_usage(self):
        provider = _provider()
        provider.client.models.generate_content.return_value = _content_response("answer", 11, 22)

        out = provider.chat(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "prior"},
            ]
        )
        assert out == "answer"
        assert provider._last_usage == {"input_tokens": 11, "output_tokens": 22}

        call = provider.client.models.generate_content.call_args
        assert call.kwargs["model"] == "gemini-2.5-flash"  # default
        contents = call.kwargs["contents"]
        # user -> "user", assistant -> "model"
        assert contents[0].role == "user"
        assert contents[1].role == "model"

    def test_chat_none_text_returns_empty(self):
        provider = _provider()
        resp = _content_response(None)
        resp.usage_metadata = None
        provider.client.models.generate_content.return_value = resp
        assert provider.chat([{"role": "user", "content": "hi"}]) == ""
        assert provider._last_usage == {"input_tokens": 0, "output_tokens": 0}


class TestAnalyzeImage:
    def test_analyze_image_returns_text(self):
        provider = _provider()
        provider.client.models.generate_content.return_value = _content_response("a chart", 90, 3)
        out = provider.analyze_image(b"\x00\x01imagebytes", "describe", model="gemini-2.5-pro")
        assert out == "a chart"
        assert provider._last_usage["input_tokens"] == 90
        assert provider.client.models.generate_content.call_args.kwargs["model"] == "gemini-2.5-pro"


class TestTranscribe:
    def test_transcribe_plain_text(self, tmp_path):
        provider = _provider()
        provider.client.models.generate_content.return_value = _content_response(
            "  the verbatim transcript  "
        )
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"\x00\x01")

        result = provider.transcribe_audio(audio, language="en")
        assert result["text"] == "the verbatim transcript"
        assert result["provider"] == "gemini"
        assert result["language"] == "en"
        assert result["segments"] == []

    def test_transcribe_unwraps_json_wrapped_text(self, tmp_path):
        """Regression: Gemini sometimes returns a JSON object despite being asked
        for plain text — the provider unwraps the inner 'text' value."""
        provider = _provider()
        provider.client.models.generate_content.return_value = _content_response(
            '{"text": "unwrapped transcript"}'
        )
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"\x00")
        result = provider.transcribe_audio(audio)
        assert result["text"] == "unwrapped transcript"

    def test_transcribe_unwraps_double_encoded_json(self, tmp_path):
        provider = _provider()
        inner = json.dumps({"text": "deep transcript"})
        provider.client.models.generate_content.return_value = _content_response(
            json.dumps({"text": inner})
        )
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"\x00")
        result = provider.transcribe_audio(audio)
        assert result["text"] == "deep transcript"

    def test_transcribe_leaves_malformed_json_untouched(self, tmp_path):
        provider = _provider()
        provider.client.models.generate_content.return_value = _content_response("{not valid json")
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"\x00")
        result = provider.transcribe_audio(audio)
        assert result["text"] == "{not valid json"

    def test_transcribe_includes_speaker_hint_in_prompt(self, tmp_path):
        provider = _provider()
        provider.client.models.generate_content.return_value = _content_response("hi")
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"\x00")
        provider.transcribe_audio(audio, speaker_hints=["Alice", "Bob"])
        prompt = provider.client.models.generate_content.call_args.kwargs["contents"][1]
        assert "Speakers: Alice, Bob." in prompt


class TestListModels:
    def _model(self, name, display=None):
        m = MagicMock()
        m.name = name
        m.display_name = display or name
        return m

    def test_list_models_strips_prefixes_and_infers_caps(self):
        provider = _provider()
        provider.client.models.list.return_value = [
            self._model("models/gemini-2.5-flash", "Gemini 2.5 Flash"),
            self._model("publishers/google/models/gemini-pro"),
            self._model("models/text-embedding-004"),
            self._model("models/imagen-3.0"),  # not gemini/embedding -> excluded
        ]
        models = provider.list_models()
        by_id = {m.id: m for m in models}

        assert "imagen-3.0" not in by_id
        assert "gemini-2.5-flash" in by_id
        assert "gemini-pro" in by_id  # publishers/ prefix stripped
        assert "chat" in by_id["gemini-2.5-flash"].capabilities
        assert "vision" in by_id["gemini-2.5-flash"].capabilities
        assert "audio" in by_id["gemini-2.5-flash"].capabilities
        assert by_id["text-embedding-004"].capabilities == ["embedding"]
        assert [m.id for m in models] == sorted(m.id for m in models)

    def test_list_models_handles_error(self):
        provider = _provider()
        provider.client.models.list.side_effect = RuntimeError("boom")
        assert provider.list_models() == []
