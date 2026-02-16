# Installation

## From PyPI

```bash
pip install planopticon
```

### Optional extras

```bash
# PDF export support
pip install planopticon[pdf]

# Google Drive + Dropbox integration
pip install planopticon[cloud]

# GPU acceleration
pip install planopticon[gpu]

# Everything
pip install planopticon[all]
```

## From source

```bash
git clone https://github.com/ConflictHQ/PlanOpticon.git
cd PlanOpticon
pip install -e ".[dev]"
```

## Binary download

Download standalone binaries (no Python required) from
[GitHub Releases](https://github.com/ConflictHQ/PlanOpticon/releases):

| Platform | Download |
|----------|----------|
| macOS (Apple Silicon) | `planopticon-macos-arm64` |
| macOS (Intel) | `planopticon-macos-x86_64` |
| Linux (x86_64) | `planopticon-linux-x86_64` |
| Windows | `planopticon-windows-x86_64.exe` |

## System dependencies

PlanOpticon requires **FFmpeg** for audio extraction:

=== "macOS"

    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu/Debian"

    ```bash
    sudo apt-get install ffmpeg libsndfile1
    ```

=== "Windows"

    Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH.

## API keys

You need at least one AI provider API key **or** a running Ollama server.

### Cloud providers

Set API keys as environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="AI..."
```

Or create a `.env` file in your project directory:

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AI...
```

### Ollama (fully offline)

No API keys needed — just install and run [Ollama](https://ollama.com):

```bash
# Install Ollama, then pull models
ollama pull llama3.2        # Chat/analysis
ollama pull llava            # Vision (diagram detection)

# Start the server (if not already running)
ollama serve
```

PlanOpticon auto-detects Ollama and uses it as a fallback when no cloud API keys are set. For a fully offline pipeline, pair Ollama with local Whisper transcription (`pip install planopticon[gpu]`).

PlanOpticon will automatically discover which providers are available and route to the best model for each task.
