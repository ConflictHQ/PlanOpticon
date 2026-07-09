# Calliope — PlanOpticon
<!-- Agent shim for https://github.com/calliopeai/calliope-cli -->

Primary conventions doc: [`bootstrap.md`](bootstrap.md)

Read it before writing any code.

---

## Project-specific notes

- Python ≥3.10 CLI (`planopticon`), Click entry point `video_processor.cli.commands:main`.
- Ruff for format + lint, line length 100. pytest with coverage on by default.
- Knowledge graph is stdlib SQLite — zero external graph deps by design.
- Optional/heavy dependencies go behind `pyproject.toml` extras with lazy imports.
- PUBLIC repo — no secrets, no SaaS internals.
