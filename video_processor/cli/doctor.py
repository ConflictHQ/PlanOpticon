"""Diagnostic checks for PlanOpticon setup."""

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

# (check_name, status, detail)
CheckResult = Tuple[str, str, str]


def check_python_version() -> CheckResult:
    """Check Python version meets minimum."""
    v = sys.version_info
    version = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 10):
        return ("Python", "ok", version)
    return ("Python", "warn", f"{version} (3.10+ recommended)")


def check_ffmpeg() -> CheckResult:
    """Check if ffmpeg is installed and accessible."""
    path = shutil.which("ffmpeg")
    if path:
        return ("FFmpeg", "ok", path)
    return ("FFmpeg", "missing", "Install via: brew install ffmpeg / apt install ffmpeg")


def check_api_keys() -> List[CheckResult]:
    """Check for configured API keys."""
    keys = {
        "OpenAI": "OPENAI_API_KEY",
        "Anthropic": "ANTHROPIC_API_KEY",
        "Google Gemini": "GEMINI_API_KEY",
        "Azure OpenAI": "AZURE_OPENAI_API_KEY",
        "Together": "TOGETHER_API_KEY",
        "Fireworks": "FIREWORKS_API_KEY",
        "Cerebras": "CEREBRAS_API_KEY",
        "xAI": "XAI_API_KEY",
        "Mistral": "MISTRAL_API_KEY",
        "Cohere": "COHERE_API_KEY",
        "HuggingFace": "HUGGINGFACE_API_KEY",
    }
    results = []
    for name, env in keys.items():
        val = os.environ.get(env, "")
        if val:
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "***"
            results.append((f"  {name}", "ok", f"{env}={masked}"))
        else:
            results.append((f"  {name}", "not set", env))
    return results


def check_ollama() -> CheckResult:
    """Check if Ollama is running locally."""
    path = shutil.which("ollama")
    if not path:
        return ("Ollama", "not installed", "Optional: https://ollama.ai")
    try:
        import subprocess

        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            models = [
                line.split()[0] for line in result.stdout.strip().split("\n")[1:] if line.strip()
            ]
            if models:
                return ("Ollama", "ok", f"{len(models)} models: {', '.join(models[:3])}")
            return ("Ollama", "ok", "Running but no models pulled")
        return ("Ollama", "warn", "Installed but not running")
    except Exception:
        return ("Ollama", "warn", "Installed but not reachable")


def check_optional_deps() -> List[CheckResult]:
    """Check optional Python dependencies."""
    deps = [
        ("reportlab", "PDF export"),
        ("pptx", "PPTX export"),
        ("markdown", "HTML reports"),
        ("torch", "GPU acceleration"),
        ("yt_dlp", "YouTube download"),
        ("feedparser", "RSS sources"),
        ("bs4", "Web scraping"),
    ]
    results = []
    for module, purpose in deps:
        try:
            __import__(module)
            results.append((f"  {module}", "ok", purpose))
        except ImportError:
            results.append((f"  {module}", "not installed", purpose))
    return results


def check_dotenv() -> CheckResult:
    """Check if .env file exists in current directory."""
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        return (".env file", "ok", str(env_path))
    return (".env file", "not found", "Run `planopticon init` to create one")


def check_knowledge_graph() -> CheckResult:
    """Check for knowledge graph files in common locations."""
    from video_processor.integrators.graph_discovery import find_nearest_graph

    path = find_nearest_graph()
    if path:
        return ("Knowledge graph", "ok", str(path))
    return ("Knowledge graph", "not found", "Run `planopticon analyze` to create one")


def run_all_checks() -> List[CheckResult]:
    """Run all diagnostic checks and return results."""
    results = []

    results.append(check_python_version())
    results.append(check_ffmpeg())
    results.append(check_dotenv())

    results.append(("API Keys", "section", ""))
    results.extend(check_api_keys())

    results.append(check_ollama())

    results.append(("Optional Dependencies", "section", ""))
    results.extend(check_optional_deps())

    results.append(check_knowledge_graph())

    return results


def format_results(results: List[CheckResult]) -> str:
    """Format check results for terminal display."""
    lines = ["", "PlanOpticon Doctor", ""]
    status_icons = {
        "ok": "[ok]",
        "warn": "[!!]",
        "missing": "[XX]",
        "not set": "[--]",
        "not found": "[--]",
        "not installed": "[--]",
        "section": "---",
    }

    any_issues = False
    for name, status, detail in results:
        icon = status_icons.get(status, "[??]")
        if status == "section":
            lines.append(f"\n{name}:")
            continue
        if status in ("missing", "warn"):
            any_issues = True
        detail_str = f"  {detail}" if detail else ""
        lines.append(f"  {icon} {name}{detail_str}")

    lines.append("")
    if any_issues:
        lines.append("Some issues found. Run `planopticon init` for guided setup.")
    else:
        has_key = any(
            s == "ok"
            for n, s, _ in results
            if n.strip()
            in (
                "OpenAI",
                "Anthropic",
                "Google Gemini",
                "Azure OpenAI",
                "Together",
                "Fireworks",
                "Cerebras",
                "xAI",
            )
        )
        if has_key:
            lines.append("Setup looks good!")
        else:
            lines.append("No API keys configured. Run `planopticon init` to set up a provider.")
    lines.append("")

    return "\n".join(lines)
