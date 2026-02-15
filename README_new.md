# PlanOpticon

Comprehensive Video Analysis & Knowledge Extraction CLI

## Overview

PlanOpticon is an advanced AI-powered CLI tool that conducts thorough analysis of video content, extracting structured knowledge, diagrams, and actionable insights. Using state-of-the-art computer vision and natural language processing techniques, PlanOpticon transforms video assets into valuable, structured information.

## Core Features

- **Complete Transcription**: Full speech-to-text with speaker attribution and semantic segmentation
- **Visual Element Extraction**: Automated recognition and digitization of diagrams, charts, whiteboards, and visual aids
- **Action Item Detection**: Intelligent identification and prioritization of tasks, commitments, and follow-ups
- **Knowledge Structure**: Organization of extracted content into searchable, related concepts
- **Plan Generation**: Synthesis of extracted elements into cohesive action plans and summaries

## Installation

### Prerequisites

- Python 3.9+
- FFmpeg (for audio/video processing)
- API keys for cloud services (OpenAI, Google Cloud, etc.)

### Setup

1. Clone the repository:

```bash
git clone https://github.com/yourusername/planopticon.git
cd planopticon
```

2. Run the setup script which creates a virtual environment and installs dependencies:

```bash
./scripts/setup.sh
```

3. Configure your API keys by editing the `.env` file created during setup.

### Manual Installation

If you prefer to set up manually:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Install optional GPU dependencies (if available)
pip install -r requirements-gpu.txt  # For NVIDIA GPUs
pip install -r requirements-apple.txt  # For Apple Silicon
```

## Usage

PlanOpticon is designed as a command-line interface tool:

```bash
# Basic usage
planopticon analyze --input video.mp4 --output analysis/

# Specify processing depth
planopticon analyze --input video.mp4 --depth comprehensive --output analysis/

# Focus on specific extraction types
planopticon analyze --input video.mp4 --focus "diagrams,action-items" --output analysis/

# Process with GPU acceleration
planopticon analyze --input video.mp4 --use-gpu --output analysis/
```

### Output Structure

```
analysis/
├── transcript/
│   ├── video_name.json    # Full transcription with timestamps and speakers
│   ├── video_name.txt     # Plain text transcription
│   └── video_name.srt     # Subtitle format
├── frames/                # Extracted key frames
│   ├── frame_0001.jpg
│   └── frame_0002.jpg
├── audio/                 # Extracted audio
│   └── video_name.wav
├── diagrams/              # Extracted and digitized visual elements
│   ├── diagram_001.svg
│   └── whiteboard_001.svg
└── cache/                 # API response cache
```

## Development

### Architecture

PlanOpticon follows a modular pipeline architecture:

```
video_processor/
├── extractors/            # Video and audio extraction
├── api/                   # Cloud API integrations
├── analyzers/             # Content analysis components
├── integrators/           # Knowledge integration
├── utils/                 # Common utilities
└── cli/                   # Command-line interface
```

### Code Standards

- Follow PEP 8 style guidelines for all Python code
- Write comprehensive docstrings using NumPy style
- Include type hints consistently throughout the codebase
- Maintain test coverage for key components

### Testing

Run tests with pytest:

```bash
pytest
```

## System Requirements

- Python 3.9+
- 8GB RAM minimum (16GB recommended)
- 2GB disk space for models and dependencies
- CUDA-compatible GPU (optional, for accelerated processing)
- ARM64 or x86_64 architecture

## License

MIT License

## Roadmap

See [work_plan.md](work_plan.md) for detailed development roadmap and milestones.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Contact

For questions or contributions, please open an issue on GitHub or contact the maintainers at your-email@example.com. 