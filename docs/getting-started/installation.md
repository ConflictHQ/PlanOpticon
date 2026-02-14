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
git clone https://github.com/conflict-llc/PlanOpticon.git
cd PlanOpticon
pip install -e ".[dev]"
```

## Binary download

Download standalone binaries (no Python required) from
[GitHub Releases](https://github.com/conflict-llc/PlanOpticon/releases):

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

You need at least one AI provider API key. Set them as environment variables:

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

PlanOpticon will automatically discover which providers are available and route to the best model for each task.
