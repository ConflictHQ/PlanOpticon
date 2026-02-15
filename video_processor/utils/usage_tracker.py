"""Usage tracking and cost estimation for API calls."""

import time
from dataclasses import dataclass, field
from typing import Optional

# Cost per million tokens (USD) — updated Feb 2025
_MODEL_PRICING = {
    # Anthropic
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-haiku-3-5-20241022": {"input": 0.80, "output": 4.00},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    # Google Gemini
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    # Whisper
    "whisper-1": {"per_minute": 0.006},
}


@dataclass
class ModelUsage:
    """Accumulated usage for a single model."""

    provider: str = ""
    model: str = ""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    audio_minutes: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost(self) -> float:
        pricing = _MODEL_PRICING.get(self.model)
        if not pricing:
            # Try partial match
            for key, p in _MODEL_PRICING.items():
                if key in self.model or self.model in key:
                    pricing = p
                    break
        if not pricing:
            return 0.0
        if "per_minute" in pricing:
            return self.audio_minutes * pricing["per_minute"]
        return (
            self.input_tokens * pricing.get("input", 0) / 1_000_000
            + self.output_tokens * pricing.get("output", 0) / 1_000_000
        )


@dataclass
class StepTiming:
    """Timing for a single pipeline step."""

    name: str
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration(self) -> float:
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0


@dataclass
class UsageTracker:
    """Tracks API usage, costs, and timing across a pipeline run."""

    _models: dict = field(default_factory=dict)
    _steps: list = field(default_factory=list)
    _current_step: Optional[StepTiming] = field(default=None)
    _start_time: float = field(default_factory=time.time)

    def record(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        audio_minutes: float = 0.0,
    ) -> None:
        """Record usage for an API call."""
        key = f"{provider}/{model}"
        if key not in self._models:
            self._models[key] = ModelUsage(provider=provider, model=model)
        usage = self._models[key]
        usage.calls += 1
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.audio_minutes += audio_minutes

    def start_step(self, name: str) -> None:
        """Start timing a pipeline step."""
        if self._current_step:
            self._current_step.end_time = time.time()
            self._steps.append(self._current_step)
        self._current_step = StepTiming(name=name, start_time=time.time())

    def end_step(self) -> None:
        """End timing the current step."""
        if self._current_step:
            self._current_step.end_time = time.time()
            self._steps.append(self._current_step)
            self._current_step = None

    @property
    def total_api_calls(self) -> int:
        return sum(u.calls for u in self._models.values())

    @property
    def total_input_tokens(self) -> int:
        return sum(u.input_tokens for u in self._models.values())

    @property
    def total_output_tokens(self) -> int:
        return sum(u.output_tokens for u in self._models.values())

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def total_cost(self) -> float:
        return sum(u.estimated_cost for u in self._models.values())

    @property
    def total_duration(self) -> float:
        return time.time() - self._start_time

    def format_summary(self) -> str:
        """Format a human-readable summary for CLI output."""
        lines = []
        lines.append("")
        lines.append("=" * 60)
        lines.append("  PROCESSING SUMMARY")
        lines.append("=" * 60)

        # Timing
        total = self.total_duration
        lines.append(f"\n  Total time: {_fmt_duration(total)}")
        if self._steps:
            lines.append("")
            max_name = max(len(s.name) for s in self._steps)
            for step in self._steps:
                pct = (step.duration / total * 100) if total > 0 else 0
                bar_len = int(pct / 3)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                lines.append(
                    f"  {step.name:<{max_name}}  {_fmt_duration(step.duration):>8}  "
                    f"{bar} {pct:4.1f}%"
                )

        # API usage
        if self._models:
            lines.append(f"\n  API Calls: {self.total_api_calls}")
            lines.append(
                f"  Tokens:    {self.total_tokens:,} "
                f"({self.total_input_tokens:,} in / {self.total_output_tokens:,} out)"
            )
            lines.append("")
            lines.append(f"  {'Model':<35} {'Calls':>6} {'In Tok':>8} {'Out Tok':>8} {'Cost':>8}")
            lines.append(f"  {'-' * 35} {'-' * 6} {'-' * 8} {'-' * 8} {'-' * 8}")
            for key in sorted(self._models.keys()):
                u = self._models[key]
                cost_str = f"${u.estimated_cost:.4f}" if u.estimated_cost > 0 else "free"
                if u.audio_minutes > 0:
                    lines.append(
                        f"  {key:<35} {u.calls:>6} {u.audio_minutes:>7.1f}m {'-':>8} {cost_str:>8}"
                    )
                else:
                    lines.append(
                        f"  {key:<35} {u.calls:>6} "
                        f"{u.input_tokens:>8,} {u.output_tokens:>8,} {cost_str:>8}"
                    )

            lines.append(f"\n  Estimated total cost: ${self.total_cost:.4f}")

        lines.append("=" * 60)
        return "\n".join(lines)


def _fmt_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m = int(seconds // 60)
    s = seconds % 60
    if m < 60:
        return f"{m}m {s:.0f}s"
    h = m // 60
    m = m % 60
    return f"{h}h {m}m {s:.0f}s"
