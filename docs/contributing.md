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

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=video_processor --cov-report=html

# Run a specific test file
pytest tests/test_models.py -v
```

## Code style

We use:

- **Ruff** for linting
- **Black** for formatting (100 char line length)
- **isort** for import sorting
- **mypy** for type checking

```bash
ruff check video_processor/
black video_processor/
isort video_processor/
mypy video_processor/ --ignore-missing-imports
```

## Project structure

See [Architecture Overview](architecture/overview.md) for the module structure.

## Adding a new provider

1. Create `video_processor/providers/your_provider.py`
2. Extend `BaseProvider` from `video_processor/providers/base.py`
3. Implement `chat()`, `analyze_image()`, `transcribe_audio()`, `list_models()`
4. Register in `video_processor/providers/discovery.py`
5. Add tests in `tests/test_providers.py`

## Adding a new cloud source

1. Create `video_processor/sources/your_source.py`
2. Implement auth flow and file listing/downloading
3. Add CLI integration in `video_processor/cli/commands.py`
4. Add tests and docs

## License

MIT License — Copyright (c) 2025 CONFLICT LLC. All rights reserved.
