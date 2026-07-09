"""Tests for the UsageTracker class."""

import time

from video_processor.utils.usage_tracker import ModelUsage, StepTiming, UsageTracker, _fmt_duration


class TestModelUsage:
    def test_total_tokens(self):
        mu = ModelUsage(provider="openai", model="gpt-4o", input_tokens=100, output_tokens=50)
        assert mu.total_tokens == 150

    def test_estimated_cost_known_model(self):
        mu = ModelUsage(
            provider="openai",
            model="gpt-4o",
            input_tokens=1_000_000,
            output_tokens=500_000,
        )
        # gpt-4o: input $2.50/M, output $10.00/M
        expected = 1_000_000 * 2.50 / 1_000_000 + 500_000 * 10.00 / 1_000_000
        assert abs(mu.estimated_cost - expected) < 0.001

    def test_estimated_cost_unknown_model(self):
        mu = ModelUsage(
            provider="local",
            model="my-custom-model",
            input_tokens=1000,
            output_tokens=500,
        )
        assert mu.estimated_cost == 0.0

    def test_estimated_cost_whisper(self):
        mu = ModelUsage(
            provider="openai",
            model="whisper-1",
            audio_minutes=10.0,
        )
        # whisper-1: $0.006/min
        assert abs(mu.estimated_cost - 0.06) < 0.001

    def test_estimated_cost_partial_match(self):
        mu = ModelUsage(
            provider="openai",
            model="gpt-4o-2024-08-06",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        # Should partial-match to gpt-4o
        assert mu.estimated_cost > 0

    def test_calls_default_zero(self):
        mu = ModelUsage()
        assert mu.calls == 0
        assert mu.total_tokens == 0
        assert mu.estimated_cost == 0.0


class TestStepTiming:
    def test_duration_with_times(self):
        st = StepTiming(name="test", start_time=100.0, end_time=105.5)
        assert abs(st.duration - 5.5) < 0.001

    def test_duration_no_end_time(self):
        st = StepTiming(name="test", start_time=100.0)
        assert st.duration == 0.0

    def test_duration_no_start_time(self):
        st = StepTiming(name="test")
        assert st.duration == 0.0


class TestUsageTracker:
    def test_record_single_call(self):
        tracker = UsageTracker()
        tracker.record("openai", "gpt-4o", input_tokens=500, output_tokens=200)
        assert tracker.total_api_calls == 1
        assert tracker.total_input_tokens == 500
        assert tracker.total_output_tokens == 200
        assert tracker.total_tokens == 700

    def test_record_multiple_calls_same_model(self):
        tracker = UsageTracker()
        tracker.record("openai", "gpt-4o", input_tokens=100, output_tokens=50)
        tracker.record("openai", "gpt-4o", input_tokens=200, output_tokens=100)
        assert tracker.total_api_calls == 2
        assert tracker.total_input_tokens == 300
        assert tracker.total_output_tokens == 150

    def test_record_multiple_models(self):
        tracker = UsageTracker()
        tracker.record("openai", "gpt-4o", input_tokens=100, output_tokens=50)
        tracker.record(
            "anthropic", "claude-sonnet-4-5-20250929", input_tokens=200, output_tokens=100
        )
        assert tracker.total_api_calls == 2
        assert tracker.total_input_tokens == 300
        assert len(tracker._models) == 2

    def test_total_cost(self):
        tracker = UsageTracker()
        tracker.record("openai", "gpt-4o", input_tokens=1_000_000, output_tokens=500_000)
        cost = tracker.total_cost
        assert cost > 0

    def test_start_and_end_step(self):
        tracker = UsageTracker()
        tracker.start_step("Frame extraction")
        time.sleep(0.01)
        tracker.end_step()

        assert len(tracker._steps) == 1
        assert tracker._steps[0].name == "Frame extraction"
        assert tracker._steps[0].duration > 0

    def test_start_step_auto_closes_previous(self):
        tracker = UsageTracker()
        tracker.start_step("Step 1")
        time.sleep(0.01)
        tracker.start_step("Step 2")
        # Step 1 should have been auto-closed
        assert len(tracker._steps) == 1
        assert tracker._steps[0].name == "Step 1"
        assert tracker._steps[0].duration > 0
        # Step 2 is current
        assert tracker._current_step.name == "Step 2"

    def test_end_step_when_none(self):
        tracker = UsageTracker()
        tracker.end_step()  # Should not raise
        assert len(tracker._steps) == 0

    def test_total_duration(self):
        tracker = UsageTracker()
        time.sleep(0.01)
        assert tracker.total_duration > 0

    def test_format_summary_empty(self):
        tracker = UsageTracker()
        summary = tracker.format_summary()
        assert "PROCESSING SUMMARY" in summary
        assert "Total time" in summary

    def test_format_summary_with_usage(self):
        tracker = UsageTracker()
        tracker.record("openai", "gpt-4o", input_tokens=1000, output_tokens=500)
        tracker.start_step("Analysis")
        tracker.end_step()

        summary = tracker.format_summary()
        assert "API Calls" in summary
        assert "Tokens" in summary
        assert "gpt-4o" in summary
        assert "Analysis" in summary

    def test_format_summary_with_audio(self):
        tracker = UsageTracker()
        tracker.record("openai", "whisper-1", audio_minutes=5.0)
        summary = tracker.format_summary()
        assert "whisper" in summary
        assert "5.0m" in summary

    def test_format_summary_cost_display(self):
        tracker = UsageTracker()
        tracker.record("openai", "gpt-4o", input_tokens=1_000_000, output_tokens=500_000)
        summary = tracker.format_summary()
        assert "Estimated total cost: $" in summary

    def test_format_summary_step_percentages(self):
        tracker = UsageTracker()
        # Manually create steps with known timings
        tracker._steps = [
            StepTiming(name="Step A", start_time=0.0, end_time=1.0),
            StepTiming(name="Step B", start_time=1.0, end_time=3.0),
        ]
        summary = tracker.format_summary()
        assert "Step A" in summary
        assert "Step B" in summary
        assert "%" in summary


class TestFmtDuration:
    def test_seconds(self):
        assert _fmt_duration(5.3) == "5.3s"

    def test_minutes(self):
        result = _fmt_duration(90.0)
        assert result == "1m 30s"

    def test_hours(self):
        result = _fmt_duration(3661.0)
        assert result == "1h 1m 1s"

    def test_zero(self):
        assert _fmt_duration(0.0) == "0.0s"

    def test_just_under_minute(self):
        assert _fmt_duration(59.9) == "59.9s"


class TestToDict:
    def test_to_dict_totals_and_breakdown(self):
        tracker = UsageTracker()
        tracker.record("openai", "gpt-4o", input_tokens=100, output_tokens=50)
        tracker.record("openai", "gpt-4o", input_tokens=10, output_tokens=5)
        tracker.record("openai", "whisper-1", audio_minutes=2.5)
        tracker.start_step("Transcription")
        tracker.end_step()

        data = tracker.to_dict()
        assert data["input_tokens"] == 110
        assert data["output_tokens"] == 55
        assert data["audio_minutes"] == 2.5
        assert data["api_calls"] == 3
        assert data["estimated_cost"] > 0
        assert data["duration_seconds"] >= 0

        models = {m["model"]: m for m in data["models"]}
        assert models["gpt-4o"]["calls"] == 2
        assert models["whisper-1"]["audio_minutes"] == 2.5
        assert data["steps"][0]["name"] == "Transcription"

    def test_to_dict_empty_tracker_and_json_serializable(self):
        import json

        data = UsageTracker().to_dict()
        assert data["input_tokens"] == 0
        assert data["models"] == []
        assert json.loads(json.dumps(data)) == data

    def test_to_dict_includes_open_step(self):
        tracker = UsageTracker()
        tracker.start_step("Frames")
        data = tracker.to_dict()
        assert [s["name"] for s in data["steps"]] == ["Frames"]
