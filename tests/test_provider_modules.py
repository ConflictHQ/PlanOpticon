"""SDK-boundary tests for optional-dependency provider modules.

Each of these providers wraps a third-party SDK that is *not* installed in the
default (dev) test environment. Rather than install every vendor SDK, we mock at
the SDK boundary only: a fake module is injected into ``sys.modules`` (or the SDK
entrypoint is patched) and the *real* provider code runs against it. Assertions
target the meaningful part -- how each provider maps our request into the SDK
call and maps the SDK response back into our shape -- plus construction guards,
error propagation, and the ProviderRegistry metadata each module registers.

Fakes live only for the duration of a ``patch.dict``/``patch.object`` context, so
they never leak into other tests.
"""

import base64
import importlib
import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import video_processor.providers.litellm_provider as litellm_module
from video_processor.providers.ai21_provider import AI21Provider
from video_processor.providers.base import ModelInfo, ProviderRegistry
from video_processor.providers.bedrock_provider import BedrockProvider
from video_processor.providers.cohere_provider import CohereProvider
from video_processor.providers.huggingface_provider import HuggingFaceProvider
from video_processor.providers.litellm_provider import LiteLLMProvider
from video_processor.providers.mistral_provider import MistralProvider
from video_processor.providers.qianfan_provider import QianfanProvider
from video_processor.providers.vertex_provider import VertexProvider
from video_processor.providers.whisper_local import WhisperLocal

USER_MSG = [{"role": "user", "content": "hello"}]


def _openai_style_response(text="hi", prompt_tokens=0, completion_tokens=0):
    """Build an object shaped like an OpenAI-compatible chat completion.

    Used by providers whose SDK returns ``resp.choices[0].message.content`` and
    ``resp.usage.{prompt,completion}_tokens`` (HF, Mistral, LiteLLM, AI21).
    """
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


# ---------------------------------------------------------------------------
# AI21 (OpenAI-compatible; SDK is `openai`, which IS installed -> patch OpenAI)
# ---------------------------------------------------------------------------


class TestAI21Provider:
    @patch.dict("os.environ", {}, clear=True)
    def test_construction_requires_api_key(self):
        with pytest.raises(ValueError, match="AI21_API_KEY"):
            AI21Provider()

    @patch("openai.OpenAI")
    def test_chat_maps_request_and_response(self, mock_openai_cls):
        client = MagicMock()
        mock_openai_cls.return_value = client
        client.chat.completions.create.return_value = _openai_style_response("jamba says hi", 7, 9)

        provider = AI21Provider(api_key="k")
        out = provider.chat(USER_MSG, max_tokens=321, temperature=0.2)

        assert out == "jamba says hi"
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "jamba-1.5-large"  # AI21 default
        assert kwargs["messages"] == USER_MSG
        assert kwargs["max_tokens"] == 321
        assert kwargs["temperature"] == 0.2
        assert provider._last_usage == {"input_tokens": 7, "output_tokens": 9}

    @patch("openai.OpenAI")
    def test_chat_honors_explicit_model(self, mock_openai_cls):
        client = MagicMock()
        mock_openai_cls.return_value = client
        client.chat.completions.create.return_value = _openai_style_response("x")

        provider = AI21Provider(api_key="k")
        provider.chat(USER_MSG, model="jamba-1.5-mini")

        assert client.chat.completions.create.call_args.kwargs["model"] == "jamba-1.5-mini"

    @patch("openai.OpenAI")
    def test_chat_propagates_errors(self, mock_openai_cls):
        client = MagicMock()
        mock_openai_cls.return_value = client
        client.chat.completions.create.side_effect = RuntimeError("boom")

        provider = AI21Provider(api_key="k")
        with pytest.raises(RuntimeError, match="boom"):
            provider.chat(USER_MSG)

    @patch("openai.OpenAI")
    def test_vision_and_transcription_unsupported(self, mock_openai_cls):
        provider = AI21Provider(api_key="k")
        with pytest.raises(NotImplementedError):
            provider.analyze_image(b"\x89PNG", "describe")
        with pytest.raises(NotImplementedError):
            provider.transcribe_audio("/tmp/a.wav")

    @patch("openai.OpenAI")
    def test_list_models_returns_curated(self, mock_openai_cls):
        provider = AI21Provider(api_key="k")
        models = provider.list_models()
        assert all(isinstance(m, ModelInfo) for m in models)
        assert {m.id for m in models} == {"jamba-1.5-large", "jamba-1.5-mini", "jamba-instruct"}
        assert all(m.provider == "ai21" for m in models)

    def test_registration_metadata(self):
        info = ProviderRegistry.all_registered()["ai21"]
        assert info["class"] is AI21Provider
        assert info["env_var"] == "AI21_API_KEY"
        assert "jamba-" in info["model_prefixes"]
        assert info["default_models"]["chat"] == "jamba-1.5-large"


# ---------------------------------------------------------------------------
# AWS Bedrock (SDK: boto3)
# ---------------------------------------------------------------------------


class _BedrockBody:
    """Stand-in for the streaming body boto3 returns under response['body']."""

    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload)


def _fake_boto3(client):
    mod = ModuleType("boto3")
    mod.client = MagicMock(return_value=client)
    return mod


class TestBedrockProvider:
    def test_construction_requires_boto3(self):
        with patch.dict(sys.modules, {"boto3": None}):
            with pytest.raises(ImportError, match="boto3"):
                BedrockProvider()

    def test_chat_maps_request_and_response(self):
        client = MagicMock()
        client.invoke_model.return_value = {
            "body": _BedrockBody(
                {
                    "content": [{"text": "bedrock says hi"}],
                    "usage": {"input_tokens": 11, "output_tokens": 22},
                }
            )
        }
        with patch.dict(sys.modules, {"boto3": _fake_boto3(client)}):
            provider = BedrockProvider()
            out = provider.chat(USER_MSG, max_tokens=256, temperature=0.3)

        assert out == "bedrock says hi"
        kwargs = client.invoke_model.call_args.kwargs
        assert kwargs["modelId"] == "anthropic.claude-3-sonnet-20240229-v1:0"  # default
        body = json.loads(kwargs["body"])
        assert body["messages"] == USER_MSG
        assert body["max_tokens"] == 256
        assert body["temperature"] == 0.3
        assert body["anthropic_version"] == "bedrock-2023-05-31"
        assert provider._last_usage == {"input_tokens": 11, "output_tokens": 22}

    def test_chat_strips_bedrock_prefix(self):
        client = MagicMock()
        client.invoke_model.return_value = {"body": _BedrockBody({"content": [{"text": "x"}]})}
        with patch.dict(sys.modules, {"boto3": _fake_boto3(client)}):
            provider = BedrockProvider()
            provider.chat(USER_MSG, model="bedrock/meta.llama3-70b-instruct-v1:0")

        assert client.invoke_model.call_args.kwargs["modelId"] == "meta.llama3-70b-instruct-v1:0"

    def test_analyze_image_encodes_base64(self):
        client = MagicMock()
        client.invoke_model.return_value = {
            "body": _BedrockBody(
                {"content": [{"text": "a cat"}], "usage": {"input_tokens": 3, "output_tokens": 1}}
            )
        }
        with patch.dict(sys.modules, {"boto3": _fake_boto3(client)}):
            provider = BedrockProvider()
            out = provider.analyze_image(b"\x89PNG", "what is this?")

        assert out == "a cat"
        body = json.loads(client.invoke_model.call_args.kwargs["body"])
        content = body["messages"][0]["content"]
        assert content[0]["source"]["data"] == base64.b64encode(b"\x89PNG").decode()
        assert content[1]["text"] == "what is this?"
        assert provider._last_usage == {"input_tokens": 3, "output_tokens": 1}

    def test_chat_propagates_errors(self):
        client = MagicMock()
        client.invoke_model.side_effect = RuntimeError("throttled")
        with patch.dict(sys.modules, {"boto3": _fake_boto3(client)}):
            provider = BedrockProvider()
            with pytest.raises(RuntimeError, match="throttled"):
                provider.chat(USER_MSG)

    def test_transcription_unsupported(self):
        with patch.dict(sys.modules, {"boto3": _fake_boto3(MagicMock())}):
            provider = BedrockProvider()
            with pytest.raises(NotImplementedError):
                provider.transcribe_audio("/tmp/a.wav")

    def test_registration_metadata(self):
        info = ProviderRegistry.all_registered()["bedrock"]
        assert info["class"] is BedrockProvider
        assert info["env_var"] == "AWS_ACCESS_KEY_ID"
        assert info["model_prefixes"] == ["bedrock/"]
        assert info["default_models"]["chat"].startswith("anthropic.claude-3-sonnet")


# ---------------------------------------------------------------------------
# Cohere (SDK: cohere)
# ---------------------------------------------------------------------------


def _fake_cohere(client):
    mod = ModuleType("cohere")
    mod.ClientV2 = MagicMock(return_value=client)
    return mod


def _cohere_response(text="hi", input_tokens=0, output_tokens=0, empty=False):
    content = [] if empty else [SimpleNamespace(text=text)]
    return SimpleNamespace(
        message=SimpleNamespace(content=content),
        usage=SimpleNamespace(
            tokens=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
        ),
    )


class TestCohereProvider:
    def test_construction_requires_sdk(self):
        with patch.dict(sys.modules, {"cohere": None}):
            with pytest.raises(ImportError, match="cohere"):
                CohereProvider()

    @patch.dict("os.environ", {}, clear=True)
    def test_construction_requires_api_key(self):
        with patch.dict(sys.modules, {"cohere": _fake_cohere(MagicMock())}):
            with pytest.raises(ValueError, match="COHERE_API_KEY"):
                CohereProvider()

    def test_chat_maps_request_and_response(self):
        client = MagicMock()
        client.chat.return_value = _cohere_response("command says hi", 4, 6)
        with patch.dict(sys.modules, {"cohere": _fake_cohere(client)}):
            provider = CohereProvider(api_key="k")
            out = provider.chat(USER_MSG, max_tokens=128, temperature=0.5)

        assert out == "command says hi"
        kwargs = client.chat.call_args.kwargs
        assert kwargs["model"] == "command-r-plus"  # default
        assert kwargs["messages"] == USER_MSG
        assert kwargs["max_tokens"] == 128
        assert kwargs["temperature"] == 0.5
        assert provider._last_usage == {"input_tokens": 4, "output_tokens": 6}

    def test_chat_empty_content_returns_empty_string(self):
        client = MagicMock()
        client.chat.return_value = _cohere_response(empty=True)
        with patch.dict(sys.modules, {"cohere": _fake_cohere(client)}):
            provider = CohereProvider(api_key="k")
            assert provider.chat(USER_MSG) == ""

    def test_chat_propagates_errors(self):
        client = MagicMock()
        client.chat.side_effect = RuntimeError("rate limit")
        with patch.dict(sys.modules, {"cohere": _fake_cohere(client)}):
            provider = CohereProvider(api_key="k")
            with pytest.raises(RuntimeError, match="rate limit"):
                provider.chat(USER_MSG)

    def test_vision_and_transcription_unsupported(self):
        with patch.dict(sys.modules, {"cohere": _fake_cohere(MagicMock())}):
            provider = CohereProvider(api_key="k")
            with pytest.raises(NotImplementedError):
                provider.analyze_image(b"x", "p")
            with pytest.raises(NotImplementedError):
                provider.transcribe_audio("/tmp/a.wav")

    def test_registration_metadata(self):
        info = ProviderRegistry.all_registered()["cohere"]
        assert info["class"] is CohereProvider
        assert info["env_var"] == "COHERE_API_KEY"
        assert info["model_prefixes"] == ["command-"]
        assert info["default_models"]["chat"] == "command-r-plus"


# ---------------------------------------------------------------------------
# Hugging Face (SDK: huggingface_hub)
# ---------------------------------------------------------------------------


def _fake_hf(client):
    mod = ModuleType("huggingface_hub")
    mod.InferenceClient = MagicMock(return_value=client)
    return mod


class TestHuggingFaceProvider:
    def test_construction_requires_sdk(self):
        with patch.dict(sys.modules, {"huggingface_hub": None}):
            with pytest.raises(ImportError, match="huggingface_hub"):
                HuggingFaceProvider()

    @patch.dict("os.environ", {}, clear=True)
    def test_construction_requires_token(self):
        with patch.dict(sys.modules, {"huggingface_hub": _fake_hf(MagicMock())}):
            with pytest.raises(ValueError, match="HF_TOKEN"):
                HuggingFaceProvider()

    def test_chat_maps_request_and_response(self):
        client = MagicMock()
        client.chat_completion.return_value = _openai_style_response("hf says hi", 5, 8)
        with patch.dict(sys.modules, {"huggingface_hub": _fake_hf(client)}):
            provider = HuggingFaceProvider(token="t")
            out = provider.chat(USER_MSG)

        assert out == "hf says hi"
        kwargs = client.chat_completion.call_args.kwargs
        assert kwargs["model"] == "meta-llama/Llama-3.1-70B-Instruct"  # default
        assert kwargs["messages"] == USER_MSG
        assert provider._last_usage == {"input_tokens": 5, "output_tokens": 8}

    def test_chat_strips_hf_prefix(self):
        client = MagicMock()
        client.chat_completion.return_value = _openai_style_response("x")
        with patch.dict(sys.modules, {"huggingface_hub": _fake_hf(client)}):
            provider = HuggingFaceProvider(token="t")
            provider.chat(USER_MSG, model="hf/mistralai/Mixtral-8x7B-Instruct-v0.1")

        assert (
            client.chat_completion.call_args.kwargs["model"]
            == "mistralai/Mixtral-8x7B-Instruct-v0.1"
        )

    def test_analyze_image_uses_llava_default(self):
        client = MagicMock()
        client.chat_completion.return_value = _openai_style_response("a dog", 2, 1)
        with patch.dict(sys.modules, {"huggingface_hub": _fake_hf(client)}):
            provider = HuggingFaceProvider(token="t")
            out = provider.analyze_image(b"\x89PNG", "what is this?")

        assert out == "a dog"
        kwargs = client.chat_completion.call_args.kwargs
        assert kwargs["model"] == "llava-hf/llava-v1.6-mistral-7b-hf"
        content = kwargs["messages"][0]["content"]
        assert content[0]["text"] == "what is this?"
        assert base64.b64encode(b"\x89PNG").decode() in content[1]["image_url"]["url"]

    def test_transcribe_maps_response(self, tmp_path):
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"\x00\x01\x02")
        client = MagicMock()
        client.automatic_speech_recognition.return_value = SimpleNamespace(text="transcribed text")
        with patch.dict(sys.modules, {"huggingface_hub": _fake_hf(client)}):
            provider = HuggingFaceProvider(token="t")
            result = provider.transcribe_audio(audio)

        assert result["text"] == "transcribed text"
        assert result["provider"] == "huggingface"
        assert result["model"] == "openai/whisper-large-v3"  # default
        assert result["segments"] == []
        assert client.automatic_speech_recognition.call_args.kwargs["audio"] == b"\x00\x01\x02"

    def test_chat_propagates_errors(self):
        client = MagicMock()
        client.chat_completion.side_effect = RuntimeError("503")
        with patch.dict(sys.modules, {"huggingface_hub": _fake_hf(client)}):
            provider = HuggingFaceProvider(token="t")
            with pytest.raises(RuntimeError, match="503"):
                provider.chat(USER_MSG)

    def test_registration_metadata(self):
        info = ProviderRegistry.all_registered()["huggingface"]
        assert info["class"] is HuggingFaceProvider
        assert info["env_var"] == "HF_TOKEN"
        assert info["model_prefixes"] == ["hf/"]
        assert info["default_models"]["audio"] == "openai/whisper-large-v3"


# ---------------------------------------------------------------------------
# Mistral (SDK: mistralai)
# ---------------------------------------------------------------------------


def _fake_mistralai(client):
    mod = ModuleType("mistralai")
    mod.Mistral = MagicMock(return_value=client)
    return mod


class TestMistralProvider:
    def test_construction_requires_sdk(self):
        with patch.dict(sys.modules, {"mistralai": None}):
            with pytest.raises(ImportError, match="mistralai"):
                MistralProvider()

    @patch.dict("os.environ", {}, clear=True)
    def test_construction_requires_api_key(self):
        with patch.dict(sys.modules, {"mistralai": _fake_mistralai(MagicMock())}):
            with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
                MistralProvider()

    def test_chat_maps_request_and_response(self):
        client = MagicMock()
        client.chat.complete.return_value = _openai_style_response("mistral says hi", 3, 5)
        with patch.dict(sys.modules, {"mistralai": _fake_mistralai(client)}):
            provider = MistralProvider(api_key="k")
            out = provider.chat(USER_MSG, max_tokens=64, temperature=0.1)

        assert out == "mistral says hi"
        kwargs = client.chat.complete.call_args.kwargs
        assert kwargs["model"] == "mistral-large-latest"  # default
        assert kwargs["messages"] == USER_MSG
        assert kwargs["max_tokens"] == 64
        assert kwargs["temperature"] == 0.1
        assert provider._last_usage == {"input_tokens": 3, "output_tokens": 5}

    def test_analyze_image_uses_pixtral_default(self):
        client = MagicMock()
        client.chat.complete.return_value = _openai_style_response("a dog", 2, 1)
        with patch.dict(sys.modules, {"mistralai": _fake_mistralai(client)}):
            provider = MistralProvider(api_key="k")
            out = provider.analyze_image(b"\x89PNG", "what is this?")

        assert out == "a dog"
        kwargs = client.chat.complete.call_args.kwargs
        assert kwargs["model"] == "pixtral-large-latest"
        content = kwargs["messages"][0]["content"]
        assert content[0]["text"] == "what is this?"
        assert base64.b64encode(b"\x89PNG").decode() in content[1]["image_url"]["url"]

    def test_transcription_unsupported(self):
        with patch.dict(sys.modules, {"mistralai": _fake_mistralai(MagicMock())}):
            provider = MistralProvider(api_key="k")
            with pytest.raises(NotImplementedError):
                provider.transcribe_audio("/tmp/a.wav")

    def test_chat_propagates_errors(self):
        client = MagicMock()
        client.chat.complete.side_effect = RuntimeError("server error")
        with patch.dict(sys.modules, {"mistralai": _fake_mistralai(client)}):
            provider = MistralProvider(api_key="k")
            with pytest.raises(RuntimeError, match="server error"):
                provider.chat(USER_MSG)

    def test_registration_metadata(self):
        info = ProviderRegistry.all_registered()["mistral"]
        assert info["class"] is MistralProvider
        assert info["env_var"] == "MISTRAL_API_KEY"
        assert "pixtral-" in info["model_prefixes"]
        assert info["default_models"]["vision"] == "pixtral-large-latest"


# ---------------------------------------------------------------------------
# Baidu Qianfan / ERNIE (SDK: qianfan)
# ---------------------------------------------------------------------------


def _fake_qianfan(chat_completion):
    mod = ModuleType("qianfan")
    mod.ChatCompletion = MagicMock(return_value=chat_completion)
    return mod


class TestQianfanProvider:
    def test_construction_requires_sdk(self):
        with patch.dict(sys.modules, {"qianfan": None}):
            with pytest.raises(ImportError, match="qianfan"):
                QianfanProvider()

    @patch.dict("os.environ", {}, clear=True)
    def test_construction_requires_both_keys(self):
        with patch.dict(sys.modules, {"qianfan": _fake_qianfan(MagicMock())}):
            with pytest.raises(ValueError, match="QIANFAN"):
                QianfanProvider()
            with pytest.raises(ValueError, match="QIANFAN"):
                QianfanProvider(access_key="a")  # secret missing
            with pytest.raises(ValueError, match="QIANFAN"):
                QianfanProvider(secret_key="s")  # access missing

    @patch.dict("os.environ", {}, clear=True)
    def test_chat_maps_request_and_response(self):
        chat_comp = MagicMock()
        chat_comp.do.return_value = {
            "result": "ernie says hi",
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
        }
        with patch.dict(sys.modules, {"qianfan": _fake_qianfan(chat_comp)}):
            provider = QianfanProvider(access_key="a", secret_key="s")
            out = provider.chat(USER_MSG, max_tokens=128, temperature=0.5)

        assert out == "ernie says hi"
        kwargs = chat_comp.do.call_args.kwargs
        assert kwargs["model"] == "ernie-4.0-8k"  # default
        assert kwargs["messages"] == USER_MSG
        assert kwargs["max_output_tokens"] == 128
        assert kwargs["temperature"] == 0.5
        assert provider._last_usage == {"input_tokens": 2, "output_tokens": 3}

    @patch.dict("os.environ", {}, clear=True)
    def test_chat_strips_qianfan_prefix(self):
        chat_comp = MagicMock()
        chat_comp.do.return_value = {"result": "x"}
        with patch.dict(sys.modules, {"qianfan": _fake_qianfan(chat_comp)}):
            provider = QianfanProvider(access_key="a", secret_key="s")
            provider.chat(USER_MSG, model="qianfan/ernie-3.5-8k")

        assert chat_comp.do.call_args.kwargs["model"] == "ernie-3.5-8k"

    @patch.dict("os.environ", {}, clear=True)
    def test_chat_propagates_errors(self):
        chat_comp = MagicMock()
        chat_comp.do.side_effect = RuntimeError("auth failed")
        with patch.dict(sys.modules, {"qianfan": _fake_qianfan(chat_comp)}):
            provider = QianfanProvider(access_key="a", secret_key="s")
            with pytest.raises(RuntimeError, match="auth failed"):
                provider.chat(USER_MSG)

    @patch.dict("os.environ", {}, clear=True)
    def test_vision_and_transcription_unsupported(self):
        with patch.dict(sys.modules, {"qianfan": _fake_qianfan(MagicMock())}):
            provider = QianfanProvider(access_key="a", secret_key="s")
            with pytest.raises(NotImplementedError):
                provider.analyze_image(b"x", "p")
            with pytest.raises(NotImplementedError):
                provider.transcribe_audio("/tmp/a.wav")

    def test_registration_metadata(self):
        info = ProviderRegistry.all_registered()["qianfan"]
        assert info["class"] is QianfanProvider
        assert info["env_var"] == "QIANFAN_ACCESS_KEY"
        assert "ernie-" in info["model_prefixes"]
        assert info["default_models"]["chat"] == "ernie-4.0-8k"


# ---------------------------------------------------------------------------
# LiteLLM (SDK: litellm). Registration is guarded on `import litellm`, so it is
# NOT registered in the default env -- the metadata test reloads with a fake.
# ---------------------------------------------------------------------------


def _fake_litellm():
    mod = ModuleType("litellm")
    mod.completion = MagicMock()
    mod.transcription = MagicMock()
    return mod


class TestLiteLLMProvider:
    def test_construction_requires_sdk(self):
        with patch.dict(sys.modules, {"litellm": None}):
            with pytest.raises(ImportError, match="litellm"):
                LiteLLMProvider()

    def test_chat_requires_explicit_model(self):
        with patch.dict(sys.modules, {"litellm": _fake_litellm()}):
            provider = LiteLLMProvider()
            with pytest.raises(ValueError, match="explicit model"):
                provider.chat(USER_MSG)

    def test_chat_maps_request_and_response(self):
        fake = _fake_litellm()
        fake.completion.return_value = _openai_style_response("litellm says hi", 6, 7)
        with patch.dict(sys.modules, {"litellm": fake}):
            provider = LiteLLMProvider()
            out = provider.chat(USER_MSG, model="openai/gpt-4o")

        assert out == "litellm says hi"
        kwargs = fake.completion.call_args.kwargs
        assert kwargs["model"] == "openai/gpt-4o"
        assert kwargs["messages"] == USER_MSG
        assert provider._last_usage == {"input_tokens": 6, "output_tokens": 7}

    def test_analyze_image_requires_model(self):
        with patch.dict(sys.modules, {"litellm": _fake_litellm()}):
            provider = LiteLLMProvider()
            with pytest.raises(ValueError, match="explicit model"):
                provider.analyze_image(b"x", "p")

    def test_transcribe_maps_response(self, tmp_path):
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"\x00")
        fake = _fake_litellm()
        fake.transcription.return_value = SimpleNamespace(text="litellm transcript")
        with patch.dict(sys.modules, {"litellm": fake}):
            provider = LiteLLMProvider()
            result = provider.transcribe_audio(audio, model="whisper-1")

        assert result["text"] == "litellm transcript"
        assert result["provider"] == "litellm"
        assert result["model"] == "whisper-1"
        assert fake.transcription.call_args.kwargs["model"] == "whisper-1"

    def test_transcribe_failure_raises_notimplemented(self, tmp_path):
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"\x00")
        fake = _fake_litellm()
        fake.transcription.side_effect = RuntimeError("unsupported")
        with patch.dict(sys.modules, {"litellm": fake}):
            provider = LiteLLMProvider()
            with pytest.raises(NotImplementedError):
                provider.transcribe_audio(audio, model="whisper-1")

    def test_chat_propagates_errors(self):
        fake = _fake_litellm()
        fake.completion.side_effect = RuntimeError("boom")
        with patch.dict(sys.modules, {"litellm": fake}):
            provider = LiteLLMProvider()
            with pytest.raises(RuntimeError, match="boom"):
                provider.chat(USER_MSG, model="openai/gpt-4o")

    def test_analyze_image_maps_request_and_response(self):
        fake = _fake_litellm()
        fake.completion.return_value = _openai_style_response("a cat", 4, 2)
        with patch.dict(sys.modules, {"litellm": fake}):
            provider = LiteLLMProvider()
            out = provider.analyze_image(b"\x89PNG", "what is this?", model="openai/gpt-4o")

        assert out == "a cat"
        kwargs = fake.completion.call_args.kwargs
        assert kwargs["model"] == "openai/gpt-4o"
        content = kwargs["messages"][0]["content"]
        assert content[0]["text"] == "what is this?"
        assert base64.b64encode(b"\x89PNG").decode() in content[1]["image_url"]["url"]
        assert provider._last_usage == {"input_tokens": 4, "output_tokens": 2}

    def test_list_models_from_sdk_model_list(self):
        fake = _fake_litellm()
        fake.model_list = ["openai/gpt-4o", "anthropic/claude-3-sonnet-20240229"]
        with patch.dict(sys.modules, {"litellm": fake}):
            provider = LiteLLMProvider()
            models = provider.list_models()

        assert [m.id for m in models] == ["openai/gpt-4o", "anthropic/claude-3-sonnet-20240229"]
        assert all(m.provider == "litellm" for m in models)

    def test_list_models_empty_without_model_list(self):
        fake = _fake_litellm()  # no model_list attribute
        with patch.dict(sys.modules, {"litellm": fake}):
            provider = LiteLLMProvider()
            assert provider.list_models() == []

    def test_registration_when_sdk_available(self):
        """litellm registers itself only when the SDK is importable. Reload the
        module with a fake `litellm` present so the guarded registration block at
        module bottom executes, then assert its metadata. The registry and module
        are restored afterward so no litellm registration leaks."""
        original = dict(ProviderRegistry._providers)
        assert "litellm" not in original  # not registered without the SDK
        try:
            with patch.dict(sys.modules, {"litellm": _fake_litellm()}):
                importlib.reload(litellm_module)
                info = ProviderRegistry.all_registered()["litellm"]
                assert info["class"] is litellm_module.LiteLLMProvider
                assert info["env_var"] == ""
                assert info["model_prefixes"] == []
                assert info["default_models"] == {"chat": "", "vision": "", "audio": ""}
        finally:
            ProviderRegistry._providers = original
            importlib.reload(litellm_module)


# ---------------------------------------------------------------------------
# Google Vertex AI (SDK: google-genai, which IS installed -> patch genai.Client
# and let the real `types` build the request objects).
# ---------------------------------------------------------------------------


def _vertex_response(text, prompt_tokens=0, candidates_tokens=0):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens, candidates_token_count=candidates_tokens
        ),
    )


class TestVertexProvider:
    @patch.dict("os.environ", {}, clear=True)
    def test_construction_requires_project(self):
        with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
            VertexProvider()

    def test_chat_maps_roles_and_response(self):
        from google import genai

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = _vertex_response("vertex says hi", 5, 6)
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "prior turn"},
        ]
        with patch.object(genai, "Client", return_value=fake_client):
            provider = VertexProvider(project="my-proj", location="us-central1")
            out = provider.chat(messages, max_tokens=256, temperature=0.4)

        assert out == "vertex says hi"
        kwargs = fake_client.models.generate_content.call_args.kwargs
        assert kwargs["model"] == "gemini-2.0-flash"  # default
        contents = kwargs["contents"]
        # user role stays "user"; any non-user role maps to "model"
        assert [c.role for c in contents] == ["user", "model"]
        assert provider._last_usage == {"input_tokens": 5, "output_tokens": 6}

    def test_chat_strips_vertex_prefix(self):
        from google import genai

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = _vertex_response("x")
        with patch.object(genai, "Client", return_value=fake_client):
            provider = VertexProvider(project="p")
            provider.chat(USER_MSG, model="vertex/gemini-1.5-pro")

        assert fake_client.models.generate_content.call_args.kwargs["model"] == "gemini-1.5-pro"

    def test_transcribe_parses_json_payload(self, tmp_path):
        from google import genai

        audio = tmp_path / "a.wav"
        audio.write_bytes(b"\x00\x01")
        payload = {
            "text": "hello world",
            "segments": [{"start": 0, "end": 1.2, "text": "hello world"}],
        }
        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = _vertex_response(
            json.dumps(payload), 10, 20
        )
        with patch.object(genai, "Client", return_value=fake_client):
            provider = VertexProvider(project="p")
            result = provider.transcribe_audio(audio, language="en")

        assert result["text"] == "hello world"
        assert result["segments"][0]["end"] == 1.2
        assert result["provider"] == "vertex"
        assert result["language"] == "en"
        assert provider._last_usage == {"input_tokens": 10, "output_tokens": 20}

    def test_transcribe_falls_back_on_non_json(self, tmp_path):
        from google import genai

        audio = tmp_path / "a.wav"
        audio.write_bytes(b"\x00")
        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = _vertex_response("not json at all")
        with patch.object(genai, "Client", return_value=fake_client):
            provider = VertexProvider(project="p")
            result = provider.transcribe_audio(audio, model="vertex/gemini-1.5-flash")

        assert result["text"] == "not json at all"
        assert result["segments"] == []
        # vertex/ prefix is stripped before the SDK call
        assert fake_client.models.generate_content.call_args.kwargs["model"] == "gemini-1.5-flash"

    def test_analyze_image_maps_request_and_response(self):
        from google import genai

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = _vertex_response("a dog", 7, 3)
        with patch.object(genai, "Client", return_value=fake_client):
            provider = VertexProvider(project="p")
            out = provider.analyze_image(b"\x89PNG", "what is this?")

        assert out == "a dog"
        kwargs = fake_client.models.generate_content.call_args.kwargs
        assert kwargs["model"] == "gemini-2.0-flash"  # default
        # the prompt is passed as the second content part (a raw string)
        assert kwargs["contents"][1] == "what is this?"
        assert provider._last_usage == {"input_tokens": 7, "output_tokens": 3}

    def test_list_models_returns_curated(self):
        from google import genai

        with patch.object(genai, "Client", return_value=MagicMock()):
            provider = VertexProvider(project="p")
            models = provider.list_models()

        assert all(isinstance(m, ModelInfo) for m in models)
        assert "gemini-2.0-flash" in {m.id for m in models}
        assert all(m.provider == "vertex" for m in models)

    def test_chat_propagates_errors(self):
        from google import genai

        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = RuntimeError("quota exceeded")
        with patch.object(genai, "Client", return_value=fake_client):
            provider = VertexProvider(project="p")
            with pytest.raises(RuntimeError, match="quota exceeded"):
                provider.chat(USER_MSG)

    def test_registration_metadata(self):
        info = ProviderRegistry.all_registered()["vertex"]
        assert info["class"] is VertexProvider
        assert info["env_var"] == "GOOGLE_CLOUD_PROJECT"
        assert info["model_prefixes"] == ["vertex/"]
        assert info["default_models"]["audio"] == "gemini-2.0-flash"


# ---------------------------------------------------------------------------
# Local Whisper (SDKs: whisper + torch, both absent in dev env)
# ---------------------------------------------------------------------------


def _fake_torch(cuda=False, mps=False):
    mod = ModuleType("torch")
    mod.cuda = SimpleNamespace(is_available=lambda: cuda)
    mod.backends = SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps))
    return mod


def _fake_whisper(model):
    mod = ModuleType("whisper")
    mod.load_model = MagicMock(return_value=model)
    return mod


class TestWhisperLocal:
    def test_is_available_false_without_deps(self):
        # torch/whisper are genuinely not installed in the dev environment.
        assert WhisperLocal.is_available() is False

    def test_is_available_true_with_deps(self):
        with patch.dict(
            sys.modules, {"torch": _fake_torch(), "whisper": _fake_whisper(MagicMock())}
        ):
            assert WhisperLocal.is_available() is True

    def test_detect_device_prefers_cuda(self):
        with patch.dict(sys.modules, {"torch": _fake_torch(cuda=True, mps=True)}):
            assert WhisperLocal._detect_device() == "cuda"

    def test_detect_device_mps_when_no_cuda(self):
        with patch.dict(sys.modules, {"torch": _fake_torch(cuda=False, mps=True)}):
            assert WhisperLocal._detect_device() == "mps"

    def test_detect_device_cpu_without_torch(self):
        with patch.dict(sys.modules, {"torch": None}):
            assert WhisperLocal._detect_device() == "cpu"

    def test_transcribe_maps_result(self, tmp_path):
        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"\x00\x01")
        model = MagicMock()
        model.transcribe.return_value = {
            "text": "  hello world  ",
            "language": "en",
            "segments": [
                {"start": 0.0, "end": 1.5, "text": " hello "},
                {"start": 1.5, "end": 3.0, "text": " world "},
            ],
        }
        with patch.dict(sys.modules, {"whisper": _fake_whisper(model)}):
            wl = WhisperLocal(model_size="base", device="cpu")
            result = wl.transcribe(audio)

        assert result["text"] == "hello world"  # stripped
        assert result["language"] == "en"
        assert result["provider"] == "whisper-local"
        assert result["model"] == "whisper-base"
        assert result["duration"] == 3.0  # last segment end
        assert result["segments"] == [
            {"start": 0.0, "end": 1.5, "text": "hello"},
            {"start": 1.5, "end": 3.0, "text": "world"},
        ]
        # cpu device -> fp16 disabled; called with the audio path as str
        args, kwargs = model.transcribe.call_args
        assert args[0] == str(audio)
        assert kwargs["fp16"] is False
        assert "language" not in kwargs

    def test_transcribe_passes_language_and_handles_no_segments(self, tmp_path):
        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"\x00")
        model = MagicMock()
        model.transcribe.return_value = {"text": "hola", "segments": [], "language": "es"}
        with patch.dict(sys.modules, {"whisper": _fake_whisper(model)}):
            wl = WhisperLocal(model_size="tiny", device="cpu")
            result = wl.transcribe(audio, language="es")

        assert model.transcribe.call_args.kwargs["language"] == "es"
        assert result["duration"] is None  # no segments

    def test_transcribe_enables_fp16_on_cuda(self, tmp_path):
        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"\x00")
        model = MagicMock()
        model.transcribe.return_value = {"text": "x", "segments": []}
        with patch.dict(sys.modules, {"whisper": _fake_whisper(model)}):
            wl = WhisperLocal(model_size="base", device="cuda")
            wl.transcribe(audio)

        assert model.transcribe.call_args.kwargs["fp16"] is True

    def test_transcribe_missing_whisper_raises(self, tmp_path):
        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"\x00")
        with patch.dict(sys.modules, {"whisper": None}):
            wl = WhisperLocal(model_size="base", device="cpu")
            with pytest.raises(ImportError, match="openai-whisper"):
                wl.transcribe(audio)
