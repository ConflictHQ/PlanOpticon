"""Tests for the provider abstraction layer."""

import importlib
from unittest.mock import MagicMock, patch

import pytest

from video_processor.providers.base import (
    BaseProvider,
    ModelInfo,
    OpenAICompatibleProvider,
    ProviderRegistry,
)
from video_processor.providers.manager import ProviderManager

# ---------------------------------------------------------------------------
# ModelInfo
# ---------------------------------------------------------------------------


class TestModelInfo:
    def test_basic(self):
        m = ModelInfo(id="gpt-4o", provider="openai", capabilities=["chat", "vision"])
        assert m.id == "gpt-4o"
        assert "vision" in m.capabilities

    def test_round_trip(self):
        m = ModelInfo(
            id="claude-sonnet-4-5-20250929",
            provider="anthropic",
            display_name="Claude Sonnet",
            capabilities=["chat", "vision"],
        )
        restored = ModelInfo.model_validate_json(m.model_dump_json())
        assert restored == m

    def test_defaults(self):
        m = ModelInfo(id="x", provider="y")
        assert m.display_name == ""
        assert m.capabilities == []


# ---------------------------------------------------------------------------
# ProviderRegistry
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    """Test ProviderRegistry class methods.

    We save and restore the internal _providers dict around each test so that
    registrations from one test don't leak into another.
    """

    @pytest.fixture(autouse=True)
    def _save_restore_registry(self):
        original = dict(ProviderRegistry._providers)
        yield
        ProviderRegistry._providers = original

    def test_register_and_get(self):
        dummy_cls = type("Dummy", (), {})
        ProviderRegistry.register("test_prov", dummy_cls, env_var="TEST_KEY")
        assert ProviderRegistry.get("test_prov") is dummy_cls

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            ProviderRegistry.get("nonexistent_provider_xyz")

    def test_get_by_model_prefix(self):
        dummy_cls = type("Dummy", (), {})
        ProviderRegistry.register("myprov", dummy_cls, model_prefixes=["mymodel-"])
        assert ProviderRegistry.get_by_model("mymodel-7b") == "myprov"
        assert ProviderRegistry.get_by_model("othermodel-7b") is None

    def test_get_by_model_returns_none_for_no_match(self):
        assert ProviderRegistry.get_by_model("totally_unknown_model_xyz") is None

    def test_available_with_env_var(self):
        dummy_cls = type("Dummy", (), {})
        ProviderRegistry.register("envprov", dummy_cls, env_var="ENVPROV_KEY")
        # Not in env -> should not appear
        with patch.dict("os.environ", {}, clear=True):
            avail = ProviderRegistry.available()
            assert "envprov" not in avail

        # In env -> should appear
        with patch.dict("os.environ", {"ENVPROV_KEY": "secret"}):
            avail = ProviderRegistry.available()
            assert "envprov" in avail

    def test_available_no_env_var_required(self):
        dummy_cls = type("Dummy", (), {})
        ProviderRegistry.register("noenvprov", dummy_cls, env_var="")
        avail = ProviderRegistry.available()
        assert "noenvprov" in avail

    def test_all_registered(self):
        dummy_cls = type("Dummy", (), {})
        ProviderRegistry.register("regprov", dummy_cls, env_var="X", default_models={"chat": "m1"})
        all_reg = ProviderRegistry.all_registered()
        assert "regprov" in all_reg
        assert all_reg["regprov"]["class"] is dummy_cls

    def test_get_default_models(self):
        dummy_cls = type("Dummy", (), {})
        ProviderRegistry.register(
            "defprov", dummy_cls, default_models={"chat": "c1", "vision": "v1"}
        )
        defaults = ProviderRegistry.get_default_models("defprov")
        assert defaults == {"chat": "c1", "vision": "v1"}

    def test_get_default_models_unknown(self):
        assert ProviderRegistry.get_default_models("unknown_prov_xyz") == {}


# ---------------------------------------------------------------------------
# ProviderManager
# ---------------------------------------------------------------------------


class TestProviderManager:
    def _make_mock_provider(self, name="openai"):
        provider = MagicMock(spec=BaseProvider)
        provider.provider_name = name
        provider.chat.return_value = "test response"
        provider.analyze_image.return_value = "image analysis"
        provider.transcribe_audio.return_value = {
            "text": "hello world",
            "segments": [],
            "provider": name,
            "model": "test",
        }
        return provider

    def test_init_with_explicit_models(self):
        mgr = ProviderManager(
            vision_model="gpt-4o",
            chat_model="claude-sonnet-4-5-20250929",
            transcription_model="whisper-1",
        )
        assert mgr.vision_model == "gpt-4o"
        assert mgr.chat_model == "claude-sonnet-4-5-20250929"
        assert mgr.transcription_model == "whisper-1"

    def test_init_forced_provider(self):
        mgr = ProviderManager(provider="gemini")
        assert mgr.vision_model == "gemini-2.5-flash"
        assert mgr.chat_model == "gemini-2.5-flash"
        assert mgr.transcription_model == "gemini-2.5-flash"

    def test_init_forced_provider_ollama(self):
        mgr = ProviderManager(provider="ollama")
        assert mgr.vision_model == ""
        assert mgr.chat_model == ""
        assert mgr.transcription_model == ""

    def test_init_no_overrides(self):
        mgr = ProviderManager()
        assert mgr.vision_model is None
        assert mgr.chat_model is None
        assert mgr.transcription_model is None
        assert mgr.auto is True

    def test_default_for_provider_gemini(self):
        result = ProviderManager._default_for_provider("gemini", "vision")
        assert result == "gemini-2.5-flash"

    def test_default_for_provider_openai(self):
        result = ProviderManager._default_for_provider("openai", "chat")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_default_for_provider_unknown(self):
        result = ProviderManager._default_for_provider("nonexistent_xyz", "chat")
        assert result == ""

    def test_provider_for_model(self):
        mgr = ProviderManager()
        assert mgr._provider_for_model("gpt-4o") == "openai"
        assert mgr._provider_for_model("claude-sonnet-4-5-20250929") == "anthropic"
        assert mgr._provider_for_model("gemini-2.5-flash") == "gemini"
        assert mgr._provider_for_model("whisper-1") == "openai"

    def test_provider_for_model_ollama_via_discovery(self):
        mgr = ProviderManager()
        mgr._available_models = [
            ModelInfo(id="llama3.2:latest", provider="ollama", capabilities=["chat"]),
        ]
        assert mgr._provider_for_model("llama3.2:latest") == "ollama"

    def test_provider_for_model_ollama_fuzzy_tag(self):
        mgr = ProviderManager()
        mgr._available_models = [
            ModelInfo(id="llama3.2:latest", provider="ollama", capabilities=["chat"]),
        ]
        assert mgr._provider_for_model("llama3.2") == "ollama"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_chat_routes_to_provider(self):
        mgr = ProviderManager(chat_model="gpt-4o")
        mock_prov = self._make_mock_provider("openai")
        mgr._providers["openai"] = mock_prov

        result = mgr.chat([{"role": "user", "content": "hello"}])
        assert result == "test response"
        mock_prov.chat.assert_called_once()

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_analyze_image_routes(self):
        mgr = ProviderManager(vision_model="gpt-4o")
        mock_prov = self._make_mock_provider("openai")
        mgr._providers["openai"] = mock_prov

        result = mgr.analyze_image(b"fake-image", "describe this")
        assert result == "image analysis"
        mock_prov.analyze_image.assert_called_once()

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_transcribe_routes(self):
        mgr = ProviderManager(transcription_model="whisper-1")
        mock_prov = self._make_mock_provider("openai")
        mgr._providers["openai"] = mock_prov

        result = mgr.transcribe_audio("/tmp/test.wav")
        assert result["text"] == "hello world"
        mock_prov.transcribe_audio.assert_called_once()

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    def test_transcribe_drops_speaker_hints_for_unsupporting_provider(self, caplog):
        """Regression for #127: --speakers with a provider whose transcribe_audio
        doesn't accept speaker_hints must warn and drop the kwarg, not crash."""

        class _NoHintsTranscriber:
            def __init__(self):
                self.calls = []

            def transcribe_audio(self, audio_path, language=None, model=None):
                self.calls.append({"language": language, "model": model})
                return {"text": "hi", "segments": [], "provider": "gemini", "model": model}

        stub = _NoHintsTranscriber()
        mgr = ProviderManager(transcription_model="gemini-2.5-flash")
        mgr._providers["gemini"] = stub

        with caplog.at_level("WARNING"):
            result = mgr.transcribe_audio("/tmp/test.wav", speaker_hints=["Alice", "Bob"])

        assert result["text"] == "hi"
        assert len(stub.calls) == 1
        assert "speaker hints" in caplog.text
        assert "speaker_hints" not in stub.calls[0]

    @patch.dict("os.environ", {"DEEPGRAM_API_KEY": "test-key"})
    def test_transcribe_passes_speaker_hints_when_supported(self):
        class _HintsTranscriber:
            def __init__(self):
                self.calls = []

            def transcribe_audio(self, audio_path, language=None, model=None, speaker_hints=None):
                self.calls.append({"speaker_hints": speaker_hints})
                return {"text": "hi", "segments": [], "provider": "deepgram", "model": model}

        stub = _HintsTranscriber()
        mgr = ProviderManager(transcription_model="nova-3")
        mgr._providers["deepgram"] = stub

        result = mgr.transcribe_audio("/tmp/test.wav", speaker_hints=["Alice", "Bob"])
        assert result["text"] == "hi"
        assert stub.calls[0]["speaker_hints"] == ["Alice", "Bob"]

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_transcribe_maps_speaker_hints_to_openai_prompt(self):
        class _PromptTranscriber:
            def __init__(self):
                self.calls = []

            def transcribe_audio(self, audio_path, language=None, model=None, prompt=None):
                self.calls.append({"prompt": prompt})
                return {"text": "hi", "segments": [], "provider": "openai", "model": model}

        stub = _PromptTranscriber()
        mgr = ProviderManager(transcription_model="whisper-1")
        mgr._providers["openai"] = stub

        mgr.transcribe_audio("/tmp/test.wav", speaker_hints=["Alice", "Bob"])
        assert stub.calls[0]["prompt"] == "Speakers: Alice, Bob."

    def test_get_models_used(self):
        mgr = ProviderManager(
            vision_model="gpt-4o",
            chat_model="claude-sonnet-4-5-20250929",
            transcription_model="whisper-1",
        )
        for name in ["openai", "anthropic"]:
            mgr._providers[name] = self._make_mock_provider(name)

        used = mgr.get_models_used()
        assert "vision" in used
        assert used["vision"] == "openai/gpt-4o"
        assert used["chat"] == "anthropic/claude-sonnet-4-5-20250929"

    def test_track_records_usage(self):
        mgr = ProviderManager(chat_model="gpt-4o")
        mock_prov = self._make_mock_provider("openai")
        mock_prov._last_usage = {"input_tokens": 10, "output_tokens": 20}
        mgr._providers["openai"] = mock_prov

        mgr.chat([{"role": "user", "content": "hi"}])
        assert mgr.usage.total_input_tokens == 10
        assert mgr.usage.total_output_tokens == 20


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider
# ---------------------------------------------------------------------------


class TestOpenAICompatibleProvider:
    @patch("openai.OpenAI")
    def test_chat(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = "hello back"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 10
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAICompatibleProvider(api_key="test", base_url="http://test")
        result = provider.chat([{"role": "user", "content": "hi"}], model="test-model")
        assert result == "hello back"
        assert provider._last_usage == {"input_tokens": 5, "output_tokens": 10}

    @patch("openai.OpenAI")
    def test_analyze_image(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = "a cat"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 5
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAICompatibleProvider(api_key="test", base_url="http://test")
        result = provider.analyze_image(b"\x89PNG", "what is this?")
        assert result == "a cat"
        assert provider._last_usage["input_tokens"] == 100

    @patch("openai.OpenAI")
    def test_transcribe_raises(self, mock_openai_cls):
        provider = OpenAICompatibleProvider(api_key="test", base_url="http://test")
        with pytest.raises(NotImplementedError):
            provider.transcribe_audio("/tmp/audio.wav")

    @patch("openai.OpenAI")
    def test_list_models(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_model = MagicMock()
        mock_model.id = "test-model-1"
        mock_client.models.list.return_value = [mock_model]

        provider = OpenAICompatibleProvider(api_key="test", base_url="http://test")
        provider.provider_name = "testprov"
        models = provider.list_models()
        assert len(models) == 1
        assert models[0].id == "test-model-1"
        assert models[0].provider == "testprov"

    @patch("openai.OpenAI")
    def test_list_models_handles_error(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.models.list.side_effect = Exception("connection error")

        provider = OpenAICompatibleProvider(api_key="test", base_url="http://test")
        models = provider.list_models()
        assert models == []


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    @patch("video_processor.providers.discovery._cached_models", None)
    @patch(
        "video_processor.providers.ollama_provider.OllamaProvider.is_available",
        return_value=False,
    )
    @patch.dict("os.environ", {}, clear=True)
    def test_discover_skips_missing_keys(self, mock_ollama):
        from video_processor.providers.discovery import discover_available_models

        models = discover_available_models(api_keys={"openai": "", "anthropic": "", "gemini": ""})
        assert models == []

    @patch.dict("os.environ", {}, clear=True)
    @patch(
        "video_processor.providers.ollama_provider.OllamaProvider.is_available",
        return_value=False,
    )
    @patch("video_processor.providers.discovery._cached_models", None)
    def test_discover_caches_results(self, mock_ollama):
        from video_processor.providers import discovery

        models = discovery.discover_available_models(
            api_keys={"openai": "", "anthropic": "", "gemini": ""}
        )
        assert models == []
        # Second call should use cache
        models2 = discovery.discover_available_models(api_keys={"openai": "key"})
        assert models2 == []  # Still cached empty result

        discovery.clear_discovery_cache()

    @patch("video_processor.providers.discovery._cached_models", None)
    @patch(
        "video_processor.providers.ollama_provider.OllamaProvider.is_available",
        return_value=False,
    )
    @patch.dict("os.environ", {}, clear=True)
    def test_force_refresh_clears_cache(self, mock_ollama):
        from video_processor.providers import discovery

        # Warm the cache
        discovery.discover_available_models(api_keys={"openai": "", "anthropic": "", "gemini": ""})
        # Force refresh should re-run
        models = discovery.discover_available_models(
            api_keys={"openai": "", "anthropic": "", "gemini": ""},
            force_refresh=True,
        )
        assert models == []

    def test_clear_discovery_cache(self):
        from video_processor.providers import discovery

        discovery._cached_models = [ModelInfo(id="x", provider="y")]
        discovery.clear_discovery_cache()
        assert discovery._cached_models is None


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


class TestOllamaProvider:
    @patch("video_processor.providers.ollama_provider.requests")
    def test_is_available_when_running(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_requests.get.return_value = mock_resp

        from video_processor.providers.ollama_provider import OllamaProvider

        assert OllamaProvider.is_available()

    @patch("video_processor.providers.ollama_provider.requests")
    def test_is_available_when_not_running(self, mock_requests):
        mock_requests.get.side_effect = ConnectionError

        from video_processor.providers.ollama_provider import OllamaProvider

        assert not OllamaProvider.is_available()

    @patch("video_processor.providers.ollama_provider.requests")
    @patch("video_processor.providers.ollama_provider.OpenAI")
    def test_transcribe_raises(self, mock_openai, mock_requests):
        from video_processor.providers.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        with pytest.raises(NotImplementedError):
            provider.transcribe_audio("/tmp/test.wav")

    @patch("video_processor.providers.ollama_provider.requests")
    @patch("video_processor.providers.ollama_provider.OpenAI")
    def test_list_models(self, mock_openai, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {"name": "llama3.2:latest", "details": {"family": "llama"}},
                {"name": "llava:13b", "details": {"family": "llava"}},
            ]
        }
        mock_requests.get.return_value = mock_resp

        from video_processor.providers.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        models = provider.list_models()
        assert len(models) == 2
        assert models[0].provider == "ollama"

        llava = [m for m in models if "llava" in m.id][0]
        assert "vision" in llava.capabilities

        llama = [m for m in models if "llama" in m.id][0]
        assert "chat" in llama.capabilities
        assert "vision" not in llama.capabilities


# ---------------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------------


class TestGeminiProvider:
    def test_transcribe_prompt_includes_speaker_hints(self, tmp_path):
        from video_processor.providers.gemini_provider import GeminiProvider

        provider = GeminiProvider(api_key="test-key")
        provider.client = MagicMock()
        response = MagicMock()
        response.text = "hello world"
        provider.client.models.generate_content.return_value = response

        audio = tmp_path / "test.wav"
        audio.write_bytes(b"\x00\x01")

        result = provider.transcribe_audio(audio, speaker_hints=["Alice", "Bob"])

        contents = provider.client.models.generate_content.call_args.kwargs["contents"]
        prompt = contents[1]
        assert "Speakers: Alice, Bob." in prompt
        assert result["text"] == "hello world"


# ---------------------------------------------------------------------------
# Provider module imports
# ---------------------------------------------------------------------------


class TestProviderImports:
    """Verify that all provider modules import without errors."""

    PROVIDER_MODULES = [
        "video_processor.providers.openai_provider",
        "video_processor.providers.anthropic_provider",
        "video_processor.providers.gemini_provider",
        "video_processor.providers.ollama_provider",
        "video_processor.providers.azure_provider",
        "video_processor.providers.together_provider",
        "video_processor.providers.fireworks_provider",
        "video_processor.providers.cerebras_provider",
        "video_processor.providers.xai_provider",
    ]

    @pytest.mark.parametrize("module_name", PROVIDER_MODULES)
    def test_import(self, module_name):
        mod = importlib.import_module(module_name)
        assert mod is not None
