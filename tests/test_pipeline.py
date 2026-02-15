"""Tests for the core video processing pipeline."""

import json
from unittest.mock import MagicMock

from video_processor.pipeline import _extract_action_items, _extract_key_points, _format_srt_time


class TestFormatSrtTime:
    def test_zero(self):
        assert _format_srt_time(0) == "00:00:00,000"

    def test_seconds(self):
        assert _format_srt_time(5.5) == "00:00:05,500"

    def test_minutes(self):
        assert _format_srt_time(90.0) == "00:01:30,000"

    def test_hours(self):
        assert _format_srt_time(3661.123) == "01:01:01,123"

    def test_large_value(self):
        result = _format_srt_time(7200.0)
        assert result == "02:00:00,000"


class TestExtractKeyPoints:
    def test_parses_valid_response(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps(
            [
                {"point": "Main point", "topic": "Architecture", "details": "Some details"},
                {"point": "Second point", "topic": None, "details": None},
            ]
        )
        result = _extract_key_points(pm, "Some transcript text here")
        assert len(result) == 2
        assert result[0].point == "Main point"
        assert result[0].topic == "Architecture"
        assert result[1].point == "Second point"

    def test_skips_invalid_items(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps(
            [
                {"point": "Valid", "topic": None},
                {"topic": "No point field"},
                {"point": "", "topic": "Empty point"},
            ]
        )
        result = _extract_key_points(pm, "text")
        assert len(result) == 1
        assert result[0].point == "Valid"

    def test_handles_error(self):
        pm = MagicMock()
        pm.chat.side_effect = Exception("API error")
        result = _extract_key_points(pm, "text")
        assert result == []

    def test_handles_non_list_response(self):
        pm = MagicMock()
        pm.chat.return_value = '{"not": "a list"}'
        result = _extract_key_points(pm, "text")
        assert result == []


class TestExtractActionItems:
    def test_parses_valid_response(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps(
            [
                {
                    "action": "Deploy fix",
                    "assignee": "Bob",
                    "deadline": "Friday",
                    "priority": "high",
                    "context": "Production",
                },
            ]
        )
        result = _extract_action_items(pm, "Some transcript text")
        assert len(result) == 1
        assert result[0].action == "Deploy fix"
        assert result[0].assignee == "Bob"

    def test_skips_invalid_items(self):
        pm = MagicMock()
        pm.chat.return_value = json.dumps(
            [
                {"action": "Valid action"},
                {"assignee": "No action field"},
                {"action": ""},
            ]
        )
        result = _extract_action_items(pm, "text")
        assert len(result) == 1

    def test_handles_error(self):
        pm = MagicMock()
        pm.chat.side_effect = Exception("API down")
        result = _extract_action_items(pm, "text")
        assert result == []
