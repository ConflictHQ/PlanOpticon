"""Tests for video_processor.utils.callbacks.WebhookCallback."""

import json
from unittest.mock import patch

import pytest

from video_processor.utils.callbacks import WebhookCallback


@pytest.fixture()
def callback():
    return WebhookCallback(url="https://example.com/webhook")


# --- Constructor ---


def test_default_headers():
    cb = WebhookCallback(url="https://example.com/hook")
    assert cb.headers == {"Content-Type": "application/json"}


def test_custom_headers():
    headers = {"Authorization": "Bearer tok", "Content-Type": "application/json"}
    cb = WebhookCallback(url="https://example.com/hook", headers=headers)
    assert cb.headers["Authorization"] == "Bearer tok"


def test_custom_timeout():
    cb = WebhookCallback(url="https://example.com/hook", timeout=5.0)
    assert cb.timeout == 5.0


# --- _post ---


@patch("urllib.request.urlopen")
@patch("urllib.request.Request")
def test_post_sends_json_payload(mock_request_cls, mock_urlopen, callback):
    callback._post({"event": "test"})

    mock_request_cls.assert_called_once()
    call_args = mock_request_cls.call_args
    data = json.loads(call_args[1]["data"] if "data" in call_args[1] else call_args[0][1])
    assert data["event"] == "test"
    mock_urlopen.assert_called_once()


@patch("urllib.request.urlopen", side_effect=Exception("Connection refused"))
@patch("urllib.request.Request")
def test_post_logs_failure_does_not_raise(mock_request_cls, mock_urlopen, callback):
    # Should not raise
    callback._post({"event": "fail_test"})


# --- on_step_start ---


@patch.object(WebhookCallback, "_post")
def test_on_step_start_payload(mock_post, callback):
    callback.on_step_start("transcription", 1, 5)

    mock_post.assert_called_once_with(
        {
            "event": "step_start",
            "step": "transcription",
            "index": 1,
            "total": 5,
        }
    )


# --- on_step_complete ---


@patch.object(WebhookCallback, "_post")
def test_on_step_complete_payload(mock_post, callback):
    callback.on_step_complete("analysis", 3, 5)

    mock_post.assert_called_once_with(
        {
            "event": "step_complete",
            "step": "analysis",
            "index": 3,
            "total": 5,
        }
    )


# --- on_progress ---


@patch.object(WebhookCallback, "_post")
def test_on_progress_payload(mock_post, callback):
    callback.on_progress("transcription", 42.5, "Processing chunk 3/7")

    mock_post.assert_called_once_with(
        {
            "event": "progress",
            "step": "transcription",
            "percent": 42.5,
            "message": "Processing chunk 3/7",
        }
    )


@patch.object(WebhookCallback, "_post")
def test_on_progress_default_message(mock_post, callback):
    callback.on_progress("extraction", 100.0)

    payload = mock_post.call_args[0][0]
    assert payload["message"] == ""
    assert payload["percent"] == 100.0
