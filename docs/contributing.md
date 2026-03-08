# Contributing

## Development setup

```bash
git clone https://github.com/ConflictHQ/PlanOpticon.git
cd PlanOpticon
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running tests

PlanOpticon has 822+ tests covering providers, pipeline stages, document processors, knowledge graph operations, exporters, skills, and CLI commands.

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=video_processor --cov-report=html

# Run a specific test file
pytest tests/test_models.py -v

# Run tests matching a keyword
pytest tests/ -k "test_knowledge_graph" -v

# Run only fast tests (skip slow integration tests)
pytest tests/ -m "not slow" -v
```

### Test conventions

- All tests live in the `tests/` directory, mirroring the `video_processor/` package structure
- Test files are named `test_<module>.py`
- Use `pytest` as the test runner -- do not use `unittest.TestCase` unless necessary for specific setup/teardown patterns
- Mock external API calls. Never make real API calls in tests. Use `unittest.mock.patch` or `pytest-mock` fixtures to mock provider responses.
- Use `tmp_path` (pytest fixture) for any tests that write files to disk
- Fixtures shared across test files go in `conftest.py`
- For testing CLI commands, use `click.testing.CliRunner`
- For testing provider implementations, mock at the HTTP client level (e.g., patch `requests.post` or the provider's SDK client)

### Mocking patterns

```python
# Mocking a provider's chat method
from unittest.mock import MagicMock, patch

def test_key_point_extraction():
    pm = MagicMock()
    pm.chat.return_value = '["Point 1", "Point 2"]'
    result = extract_key_points(pm, "transcript text")
    assert len(result) == 2

# Mocking an external API at the HTTP level
@patch("requests.post")
def test_provider_chat(mock_post):
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "response"}}]
    }
    provider = OpenAIProvider(api_key="test")
    result = provider.chat([{"role": "user", "content": "hello"}])
    assert result == "response"
```

## Code style

We use:

- **Ruff** for both linting and formatting (100 char line length)
- **mypy** for type checking

Ruff handles all linting (error, warning, pyflakes, and import sorting rules) and formatting in a single tool. There is no need to run Black or isort separately.

```bash
# Lint
ruff check video_processor/

# Format
ruff format video_processor/

# Auto-fix lint issues
ruff check video_processor/ --fix

# Type check
mypy video_processor/ --ignore-missing-imports
```

### Ruff configuration

The project's `pyproject.toml` configures ruff as follows:

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
```

The `I` rule set covers import sorting (equivalent to isort), so imports are automatically organized by ruff.

## Project structure

```
PlanOpticon/
├── video_processor/
│   ├── cli/                   # Click CLI commands
│   │   └── commands.py
│   ├── providers/             # LLM/API provider implementations
│   │   ├── base.py            # BaseProvider, ProviderRegistry
│   │   ├── manager.py         # ProviderManager
│   │   ├── discovery.py       # Auto-discovery of available providers
│   │   ├── openai_provider.py
│   │   ├── anthropic_provider.py
│   │   ├── gemini_provider.py
│   │   └── ...                # 15+ provider implementations
│   ├── sources/               # Cloud and web source connectors
│   │   ├── base.py            # BaseSource, SourceFile
│   │   ├── google_drive.py
│   │   ├── zoom_source.py
│   │   └── ...                # 20+ source implementations
│   ├── processors/            # Document processors
│   │   ├── base.py            # DocumentProcessor, registry
│   │   ├── ingest.py          # File/directory ingestion
│   │   ├── markdown_processor.py
│   │   ├── pdf_processor.py
│   │   └── __init__.py        # Auto-registration of built-in processors
│   ├── integrators/           # Knowledge graph and analysis
│   │   ├── knowledge_graph.py # KnowledgeGraph class
│   │   ├── graph_store.py     # SQLite graph storage
│   │   ├── graph_query.py     # GraphQueryEngine
│   │   ├── graph_discovery.py # Auto-find knowledge_graph.db
│   │   └── taxonomy.py        # Planning taxonomy classifier
│   ├── agent/                 # Planning agent
│   │   ├── orchestrator.py    # Agent orchestration
│   │   └── skills/            # Skill implementations
│   │       ├── base.py        # Skill ABC, registry, Artifact
│   │       ├── project_plan.py
│   │       ├── prd.py
│   │       ├── roadmap.py
│   │       ├── task_breakdown.py
│   │       ├── doc_generator.py
│   │       ├── wiki_generator.py
│   │       ├── notes_export.py
│   │       ├── artifact_export.py
│   │       ├── github_integration.py
│   │       ├── requirements_chat.py
│   │       ├── cli_adapter.py
│   │       └── __init__.py    # Auto-registration of skills
│   ├── exporters/             # Output format exporters
│   │   ├── __init__.py
│   │   └── markdown.py        # Template-based markdown generation
│   ├── utils/                 # Shared utilities
│   │   ├── export.py          # Multi-format export orchestration
│   │   ├── rendering.py       # Mermaid/chart rendering
│   │   ├── prompt_templates.py
│   │   ├── callbacks.py       # Progress callback helpers
│   │   └── ...
│   ├── exchange.py            # PlanOpticonExchange format
│   ├── pipeline.py            # Main video processing pipeline
│   ├── models.py              # Pydantic data models
│   └── output_structure.py    # Output directory helpers
├── tests/                     # 822+ tests
├── knowledge-base/            # Local-first graph tools
│   ├── viewer.html            # Self-contained D3.js graph viewer
│   └── query.py               # Python query script (NetworkX)
├── docs/                      # MkDocs documentation
└── pyproject.toml             # Project configuration
```

See [Architecture Overview](architecture/overview.md) for a more detailed breakdown of module responsibilities.

## Adding a new provider

Providers self-register via `ProviderRegistry.register()` at module level. When the provider module is imported, it registers itself automatically.

1. Create `video_processor/providers/your_provider.py`
2. Extend `BaseProvider` from `video_processor/providers/base.py`
3. Implement the four required methods: `chat()`, `analyze_image()`, `transcribe_audio()`, `list_models()`
4. Call `ProviderRegistry.register()` at module level
5. Add the import to `video_processor/providers/manager.py` in the lazy-import block
6. Add tests in `tests/test_providers.py`

### Example provider skeleton

```python
"""Your provider implementation."""

from video_processor.providers.base import BaseProvider, ModelInfo, ProviderRegistry


class YourProvider(BaseProvider):
    provider_name = "yourprovider"

    def __init__(self, api_key: str | None = None):
        import os
        self.api_key = api_key or os.environ.get("YOUR_API_KEY", "")

    def chat(self, messages, max_tokens=4096, temperature=0.7, model=None):
        # Implement chat completion
        ...

    def analyze_image(self, image_bytes, prompt, max_tokens=4096, model=None):
        # Implement image analysis
        ...

    def transcribe_audio(self, audio_path, language=None, model=None):
        # Implement audio transcription (or raise NotImplementedError)
        ...

    def list_models(self):
        return [ModelInfo(id="your-model", provider="yourprovider", capabilities=["chat"])]


# Self-registration at import time
ProviderRegistry.register(
    "yourprovider",
    YourProvider,
    env_var="YOUR_API_KEY",
    model_prefixes=["your-"],
    default_models={"chat": "your-model"},
)
```

### OpenAI-compatible providers

For providers that use the OpenAI API format, extend `OpenAICompatibleProvider` instead of `BaseProvider`. This provides default implementations of `chat()`, `analyze_image()`, and `list_models()` -- you only need to configure the base URL and model mappings.

```python
from video_processor.providers.base import OpenAICompatibleProvider, ProviderRegistry

class YourProvider(OpenAICompatibleProvider):
    provider_name = "yourprovider"
    base_url = "https://api.yourprovider.com/v1"
    env_var = "YOUR_API_KEY"

ProviderRegistry.register("yourprovider", YourProvider, env_var="YOUR_API_KEY")
```

## Adding a new cloud source

Source connectors implement the `BaseSource` ABC from `video_processor/sources/base.py`. Authentication is handled per-source, typically via environment variables.

1. Create `video_processor/sources/your_source.py`
2. Extend `BaseSource`
3. Implement `authenticate()`, `list_videos()`, and `download()`
4. Add the class to the lazy-import map in `video_processor/sources/__init__.py`
5. Add CLI commands in `video_processor/cli/commands.py` if needed
6. Add tests and documentation

### Example source skeleton

```python
"""Your source integration."""

import os
import logging
from pathlib import Path
from typing import List, Optional

from video_processor.sources.base import BaseSource, SourceFile

logger = logging.getLogger(__name__)


class YourSource(BaseSource):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("YOUR_SOURCE_KEY", "")

    def authenticate(self) -> bool:
        """Validate credentials. Return True on success."""
        if not self.api_key:
            logger.error("API key not set. Set YOUR_SOURCE_KEY env var.")
            return False
        # Make a test API call to verify credentials
        ...
        return True

    def list_videos(
        self,
        folder_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> List[SourceFile]:
        """List available video files."""
        ...

    def download(self, file: SourceFile, destination: Path) -> Path:
        """Download a single file. Return the local path."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Download file content to destination
        ...
        return destination
```

### Registering in `__init__.py`

Add your source to the `__all__` list and the `_lazy_map` dictionary in `video_processor/sources/__init__.py`:

```python
__all__ = [
    ...
    "YourSource",
]

_lazy_map = {
    ...
    "YourSource": "video_processor.sources.your_source",
}
```

## Adding a new skill

Agent skills extend the `Skill` ABC from `video_processor/agent/skills/base.py` and self-register via `register_skill()`.

1. Create `video_processor/agent/skills/your_skill.py`
2. Extend `Skill` and set `name` and `description` class attributes
3. Implement `execute()` to return an `Artifact`
4. Optionally override `can_execute()` for custom precondition checks
5. Call `register_skill()` at module level
6. Add the import to `video_processor/agent/skills/__init__.py`
7. Add tests

### Example skill skeleton

```python
"""Your custom skill."""

from video_processor.agent.skills.base import AgentContext, Artifact, Skill, register_skill


class YourSkill(Skill):
    name = "your_skill"
    description = "Generates a custom artifact from the knowledge graph."

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        """Generate the artifact."""
        kg_data = context.knowledge_graph.to_dict()
        # Build content from knowledge graph data
        content = f"# Your Artifact\n\n{len(kg_data.get('entities', []))} entities found."
        return Artifact(
            name="your_artifact",
            content=content,
            artifact_type="document",
            format="markdown",
        )

    def can_execute(self, context: AgentContext) -> bool:
        """Check prerequisites (default requires KG + provider)."""
        return context.knowledge_graph is not None


# Self-registration at import time
register_skill(YourSkill())
```

### Registering in `__init__.py`

Add the import to `video_processor/agent/skills/__init__.py` so the skill is loaded (and self-registered) when the skills package is imported:

```python
from video_processor.agent.skills import (
    ...
    your_skill,  # noqa: F401
)
```

## Adding a new document processor

Document processors extend the `DocumentProcessor` ABC from `video_processor/processors/base.py` and are registered via `register_processor()`.

1. Create `video_processor/processors/your_processor.py`
2. Extend `DocumentProcessor`
3. Set `supported_extensions` class attribute
4. Implement `process()` (returns `List[DocumentChunk]`) and `can_process()`
5. Call `register_processor()` at module level
6. Add the import to `video_processor/processors/__init__.py`
7. Add tests

### Example processor skeleton

```python
"""Your document processor."""

from pathlib import Path
from typing import List

from video_processor.processors.base import (
    DocumentChunk,
    DocumentProcessor,
    register_processor,
)


class YourProcessor(DocumentProcessor):
    supported_extensions = [".xyz", ".abc"]

    def can_process(self, path: Path) -> bool:
        return path.suffix.lower() in self.supported_extensions

    def process(self, path: Path) -> List[DocumentChunk]:
        text = path.read_text()
        # Split into chunks as appropriate for your format
        return [
            DocumentChunk(
                text=text,
                source_file=str(path),
                chunk_index=0,
                metadata={"format": "xyz"},
            )
        ]


# Self-registration at import time
register_processor([".xyz", ".abc"], YourProcessor)
```

### Registering in `__init__.py`

Add the import to `video_processor/processors/__init__.py`:

```python
from video_processor.processors import (
    markdown_processor,  # noqa: F401, E402
    pdf_processor,       # noqa: F401, E402
    your_processor,      # noqa: F401, E402
)
```

## Adding a new exporter

Exporters live in `video_processor/exporters/` and are typically called from CLI commands. There is no strict ABC for exporters -- they are plain functions that accept knowledge graph data and an output directory.

1. Create `video_processor/exporters/your_exporter.py`
2. Implement one or more export functions that accept KG data (as a dict) and an output path
3. Add CLI integration in `video_processor/cli/commands.py` under the `export` group
4. Add tests

### Example exporter skeleton

```python
"""Your exporter."""

import json
from pathlib import Path
from typing import List


def export_your_format(kg_data: dict, output_dir: Path) -> List[Path]:
    """Export knowledge graph data in your format.

    Args:
        kg_data: Knowledge graph as a dict (from KnowledgeGraph.to_dict()).
        output_dir: Directory to write output files.

    Returns:
        List of created file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    created = []

    output_file = output_dir / "export.xyz"
    output_file.write_text(json.dumps(kg_data, indent=2))
    created.append(output_file)

    return created
```

### Adding the CLI command

Add a subcommand under the `export` group in `video_processor/cli/commands.py`:

```python
@export.command("your-format")
@click.argument("db_path", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None)
def export_your_format_cmd(db_path, output):
    """Export knowledge graph in your format."""
    from video_processor.exporters.your_exporter import export_your_format
    from video_processor.integrators.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph(db_path=Path(db_path))
    out_dir = Path(output) if output else Path.cwd() / "your-export"
    created = export_your_format(kg.to_dict(), out_dir)
    click.echo(f"Exported {len(created)} files to {out_dir}/")
```

## License

MIT License -- Copyright (c) 2026 CONFLICT LLC. All rights reserved.
