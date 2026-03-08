"""Interactive setup wizard for PlanOpticon."""

import os
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple

import click

PROVIDERS = [
    ("openai", "OpenAI", "OPENAI_API_KEY"),
    ("anthropic", "Anthropic", "ANTHROPIC_API_KEY"),
    ("gemini", "Google Gemini", "GEMINI_API_KEY"),
    ("ollama", "Ollama (local)", None),
    ("azure", "Azure OpenAI", "AZURE_OPENAI_API_KEY"),
    ("together", "Together AI", "TOGETHER_API_KEY"),
    ("fireworks", "Fireworks AI", "FIREWORKS_API_KEY"),
    ("cerebras", "Cerebras", "CEREBRAS_API_KEY"),
    ("xai", "xAI", "XAI_API_KEY"),
]


def _check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _test_provider(provider_id: str, api_key: Optional[str] = None) -> Tuple[bool, str]:
    """Test that a provider connection works."""
    if provider_id == "ollama":
        try:
            import subprocess

            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True, "Ollama is running"
            return False, "Ollama is installed but not running. Start with: ollama serve"
        except FileNotFoundError:
            return False, "Ollama not found. Install from: https://ollama.ai"
        except Exception as e:
            return False, f"Could not reach Ollama: {e}"

    if not api_key:
        return False, "No API key provided"

    # For API-based providers, just check the key looks valid
    if len(api_key) < 8:
        return False, "API key looks too short"
    return True, "API key configured"


def run_wizard() -> None:
    """Run the interactive setup wizard."""
    click.echo()
    click.echo("  PlanOpticon Setup Wizard")
    click.echo("  " + "-" * 30)
    click.echo()

    # Step 1: Check prerequisites
    click.echo("Checking prerequisites...")
    click.echo()

    if _check_ffmpeg():
        click.echo("  [ok] FFmpeg found")
    else:
        click.echo("  [!!] FFmpeg not found")
        click.echo("       Install: brew install ffmpeg (macOS)")
        click.echo("                apt install ffmpeg (Ubuntu)")
        click.echo("                winget install ffmpeg (Windows)")
        click.echo()

    # Step 2: Choose provider
    click.echo()
    click.echo("Choose your AI provider:")
    click.echo()
    for i, (pid, name, _) in enumerate(PROVIDERS, 1):
        # Check if already configured
        env_key = PROVIDERS[i - 1][2]
        status = ""
        if pid == "ollama":
            if shutil.which("ollama"):
                status = " (installed)"
        elif env_key and os.environ.get(env_key):
            status = " (configured)"
        click.echo(f"  {i}. {name}{status}")
    click.echo()

    choice = click.prompt(
        "Select provider",
        type=click.IntRange(1, len(PROVIDERS)),
        default=1,
    )
    provider_id, provider_name, env_var = PROVIDERS[choice - 1]

    # Step 3: Configure API key
    env_vars: Dict[str, str] = {}

    if provider_id == "ollama":
        click.echo()
        ok, msg = _test_provider("ollama")
        if ok:
            click.echo(f"  [ok] {msg}")
        else:
            click.echo(f"  [!!] {msg}")
    elif env_var:
        existing = os.environ.get(env_var, "")
        if existing:
            click.echo(f"\n  {env_var} is already set.")
            if not click.confirm("  Update it?", default=False):
                env_vars[env_var] = existing
            else:
                key = click.prompt(f"  Enter {env_var}", hide_input=True)
                env_vars[env_var] = key
        else:
            click.echo(f"\n  {provider_name} requires {env_var}.")
            key = click.prompt(f"  Enter {env_var}", hide_input=True)
            env_vars[env_var] = key

        if env_var in env_vars:
            ok, msg = _test_provider(provider_id, env_vars[env_var])
            if ok:
                click.echo(f"  [ok] {msg}")
            else:
                click.echo(f"  [!!] {msg}")

    # Step 4: Additional providers?
    click.echo()
    if click.confirm("Configure additional providers?", default=False):
        for pid, pname, evar in PROVIDERS:
            if pid == provider_id or not evar:
                continue
            if os.environ.get(evar):
                continue
            if click.confirm(f"  Set up {pname}?", default=False):
                key = click.prompt(f"    Enter {evar}", hide_input=True)
                env_vars[evar] = key

    # Step 5: Write .env file
    env_path = Path.cwd() / ".env"
    if env_vars:
        click.echo()

        if env_path.exists():
            click.echo(f"  .env already exists at {env_path}")
            if not click.confirm("  Append new keys?", default=True):
                click.echo("  Skipping .env update.")
                _print_summary(provider_name, env_vars)
                return

        # Read existing content
        existing_content = env_path.read_text() if env_path.exists() else ""
        existing_keys = set()
        for line in existing_content.split("\n"):
            if "=" in line and not line.strip().startswith("#"):
                existing_keys.add(line.split("=", 1)[0].strip())

        new_lines = []
        for key, val in env_vars.items():
            if key not in existing_keys:
                new_lines.append(f"{key}={val}")

        if new_lines:
            with open(env_path, "a") as f:
                if existing_content and not existing_content.endswith("\n"):
                    f.write("\n")
                f.write("\n".join(new_lines) + "\n")
            click.echo(f"  Updated {env_path} with {len(new_lines)} key(s)")
        else:
            click.echo("  All keys already in .env")

        # Remind about .gitignore
        gitignore = Path.cwd() / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            if ".env" not in content:
                click.echo("  [!!] .env is not in .gitignore — consider adding it")
        else:
            click.echo("  [!!] No .gitignore found — make sure .env is not committed")

    _print_summary(provider_name, env_vars)


def _print_summary(provider_name: str, env_vars: Dict[str, str]) -> None:
    """Print setup summary."""
    click.echo()
    click.echo("  Setup complete!")
    click.echo()
    click.echo(f"  Provider: {provider_name}")
    if env_vars:
        click.echo(f"  Keys configured: {len(env_vars)}")
    click.echo()
    click.echo("  Next steps:")
    click.echo("    planopticon doctor        Check setup health")
    click.echo("    planopticon analyze -i VIDEO -o OUTPUT")
    click.echo("    planopticon -I            Interactive mode")
    click.echo()
