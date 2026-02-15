# Contributing to PlanOpticon

Thank you for your interest in contributing to PlanOpticon! This guide will help you get started.

## Development Setup

1. **Fork and clone the repository:**

   ```bash
   git clone https://github.com/<your-username>/PlanOpticon.git
   cd PlanOpticon
   ```

2. **Create a virtual environment:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install in editable mode with dev dependencies:**

   ```bash
   pip install -e ".[dev]"
   ```

4. **Install FFmpeg** (required for video processing):

   ```bash
   # macOS
   brew install ffmpeg

   # Ubuntu/Debian
   sudo apt install ffmpeg
   ```

5. **Set up at least one AI provider API key:**

   ```bash
   export OPENAI_API_KEY="sk-..."
   # or
   export ANTHROPIC_API_KEY="sk-ant-..."
   # or
   export GEMINI_API_KEY="..."
   ```

## Running Tests

```bash
pytest tests/
```

To run tests with coverage:

```bash
pytest tests/ --cov=video_processor
```

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

**Check for lint issues:**

```bash
ruff check .
```

**Auto-fix lint issues:**

```bash
ruff check --fix .
```

**Format code:**

```bash
ruff format .
```

**Verify formatting (without modifying files):**

```bash
ruff format --check .
```

The project targets a line length of 100 characters and Python 3.10+. See `pyproject.toml` for the full Ruff configuration.

## Commit Conventions

Write clear, descriptive commit messages. Use the imperative mood in the subject line:

- `Add knowledge graph merging for batch mode`
- `Fix frame extraction crash on zero-length videos`
- `Update API provider discovery to handle rate limits`

Keep the subject line under 72 characters. Use the body to explain *what* and *why*, not *how*.

## Pull Request Process

1. **Create a branch** from `main` for your work:

   ```bash
   git checkout -b your-branch-name
   ```

2. **Make your changes.** Write tests for new functionality and ensure existing tests still pass.

3. **Lint and format** your code before committing:

   ```bash
   ruff check .
   ruff format .
   ```

4. **Push your branch** and open a pull request against `main`.

5. **Fill out the PR template.** Describe your changes, the type of change, and your test plan.

6. **Address review feedback.** A maintainer will review your PR and may request changes. We aim to review PRs within a few business days.

## Reporting Bugs and Requesting Features

- **Bugs:** Open an issue using the [Bug Report](https://github.com/ConflictHQ/PlanOpticon/issues/new?template=bug_report.yml) template.
- **Features:** Open an issue using the [Feature Request](https://github.com/ConflictHQ/PlanOpticon/issues/new?template=feature_request.yml) template.
- **Questions:** Start a thread in [Discussions](https://github.com/ConflictHQ/PlanOpticon/discussions).

## Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold it.

## Security

If you discover a security vulnerability, please do **not** open a public issue. Instead, follow the process described in our [Security Policy](SECURITY.md).

## License

By contributing to PlanOpticon, you agree that your contributions will be licensed under the [MIT License](../LICENSE).
