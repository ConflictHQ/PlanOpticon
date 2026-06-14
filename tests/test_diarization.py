"""Tests for the diarizing transcribers (Deepgram, ElevenLabs) and the
ProviderManager diarization routing."""

from unittest.mock import MagicMock, patch

from video_processor.providers.base import BaseProvider
from video_processor.providers.deepgram_provider import DeepgramProvider
from video_processor.providers.elevenlabs_provider import ElevenLabsProvider
from video_processor.providers.manager import ProviderManager


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _dummy_wav(tmp_path):
    p = tmp_path / "a.wav"
    p.write_bytes(b"\x00\x01")
    return str(p)


class TestDeepgramProvider:
    def test_parses_speaker_labeled_utterances(self, tmp_path):
        payload = {
            "metadata": {"duration": 4.0},
            "results": {
                "channels": [
                    {
                        "alternatives": [{"transcript": "Hello there. Hi back."}],
                        "detected_language": "en",
                    }
                ],
                "utterances": [
                    {"start": 0.0, "end": 2.0, "transcript": "Hello there.", "speaker": 0},
                    {"start": 2.5, "end": 4.0, "transcript": "Hi back.", "speaker": 1},
                ],
            },
        }
        with patch(
            "video_processor.providers.deepgram_provider.requests.post",
            return_value=_mock_response(payload),
        ):
            result = DeepgramProvider(api_key="x").transcribe_audio(
                _dummy_wav(tmp_path), diarize=True
            )

        assert result["provider"] == "deepgram"
        assert result["duration"] == 4.0
        speakers = [s["speaker"] for s in result["segments"]]
        assert speakers == ["Speaker 0", "Speaker 1"]
        assert result["segments"][0]["text"] == "Hello there."

    def test_no_speaker_field_when_diarize_off(self, tmp_path):
        payload = {
            "metadata": {"duration": 2.0},
            "results": {
                "channels": [{"alternatives": [{"transcript": "Just text."}]}],
                "utterances": [
                    {"start": 0.0, "end": 2.0, "transcript": "Just text.", "speaker": 0}
                ],
            },
        }
        with patch(
            "video_processor.providers.deepgram_provider.requests.post",
            return_value=_mock_response(payload),
        ):
            result = DeepgramProvider(api_key="x").transcribe_audio(
                _dummy_wav(tmp_path), diarize=False
            )
        assert "speaker" not in result["segments"][0]


class TestElevenLabsProvider:
    def test_groups_words_into_speaker_turns(self, tmp_path):
        payload = {
            "text": "Hello there. Hi back.",
            "language_code": "en",
            "words": [
                {
                    "type": "word",
                    "text": "Hello",
                    "start": 0.0,
                    "end": 0.5,
                    "speaker_id": "speaker_0",
                },
                {"type": "spacing", "text": " "},
                {
                    "type": "word",
                    "text": "there.",
                    "start": 0.5,
                    "end": 1.0,
                    "speaker_id": "speaker_0",
                },
                {"type": "word", "text": "Hi", "start": 2.5, "end": 2.8, "speaker_id": "speaker_1"},
                {"type": "spacing", "text": " "},
                {
                    "type": "word",
                    "text": "back.",
                    "start": 2.8,
                    "end": 3.2,
                    "speaker_id": "speaker_1",
                },
            ],
        }
        with patch(
            "video_processor.providers.elevenlabs_provider.requests.post",
            return_value=_mock_response(payload),
        ):
            result = ElevenLabsProvider(api_key="x").transcribe_audio(
                _dummy_wav(tmp_path), diarize=True
            )

        assert result["provider"] == "elevenlabs"
        assert [s["speaker"] for s in result["segments"]] == ["Speaker 0", "Speaker 1"]
        assert result["segments"][0]["text"] == "Hello there."
        assert result["segments"][1]["text"] == "Hi back."


class TestDiarizeRouting:
    def _mock_provider(self, name):
        prov = MagicMock(spec=BaseProvider)
        prov.transcribe_audio.return_value = {
            "text": "x",
            "segments": [],
            "duration": 1.0,
            "provider": name,
            "model": "m",
        }
        return prov

    def test_diarize_routes_to_capable_provider(self):
        mgr = ProviderManager(transcription_model="nova-3")
        prov = self._mock_provider("deepgram")
        mgr._providers["deepgram"] = prov

        mgr.transcribe_audio("/tmp/a.wav", diarize=True)

        prov.transcribe_audio.assert_called_once()
        assert prov.transcribe_audio.call_args.kwargs.get("diarize") is True

    def test_non_capable_transcriber_falls_back_without_diarize(self):
        # openai can't diarize → manager should not call it with diarize and
        # should fall through to the normal (non-diarized) path.
        mgr = ProviderManager(transcription_model="whisper-1")
        prov = self._mock_provider("openai")
        mgr._providers["openai"] = prov

        mgr.transcribe_audio("/tmp/a.wav", diarize=True)

        assert prov.transcribe_audio.call_args.kwargs.get("diarize") is None
