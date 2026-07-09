# Changelog

All notable changes to PlanOpticon are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-08

First stable release. The CLI surface, provider registry, output layout, and
interchange contracts (`conflict-kg/v1`, PlanOpticonExchange, `usage.json`)
are now stable interfaces consumed by external tools — breaking changes from
here follow semver.

### Added

- **conflict-kg/v1 canonical graph export** (`planopticon export conflict-kg DB_PATH [--sqlite]`): one interchange contract for every Conflict tool — JSON encoding for small/medium graphs and a Cloudflare D1-compatible SQLite encoding for large ones. Node ids are stable case-insensitive identity keys; edges reference ids for O(1) loading.
- **Speaker diarization backends**: Deepgram (nova-3) and ElevenLabs (scribe_v1) transcribers with `--diarize`, producing per-segment speaker labels.
- **Machine-readable usage artifact**: every pipeline run now writes `usage.json` (tokens, audio minutes, per-model cost estimates, step timings) alongside the manifest — the cost-tracking contract for the hosted platform.

### Fixed

- `--speakers` no longer crashes providers that don't accept speaker hints (Gemini and others); hints are passed only where supported, mapped into the OpenAI Whisper prompt (which previously never received them), and woven into Gemini's transcription prompt.
- Pinned `opencv-python < 5` — OpenCV 5.0 removed `cv2.CascadeClassifier` and broke frame extraction.

### Documentation

- `bootstrap.md` conventions document plus agent shims (`CLAUDE.md`, `AGENTS.md`, `CALLIOPE.md`).
- Knowledge Graphs guide documents the SQLite→Navegador ingest handoff as the supported default topology.

## [0.6.0] - 2026-04-13

### Fixed

- Aligned public output-format docs with the emitted JSON schemas for `knowledge_graph.json`, `key_points.json`, and `action_items.json`.
- Updated PlanOpticonExchange docs to use the emitted `version` field instead of `schema_version`.
- Corrected batch output docs and CLI messaging to point at the batch root `manifest.json`.

## [0.4.0] - 2026-03-07

### Added

- **Planning agent framework** with 11 skills: project_plan, prd, roadmap, task_breakdown, github_integration, requirements_chat, doc_generator, artifact_export, cli_adapter, notes_export, wiki_generator. Invoke via `planopticon agent`.
- **Interactive companion REPL** (`planopticon companion` / `planopticon --chat`) with auto-discovery of knowledge graphs, videos, and documents in the workspace. 15 slash commands for graph exploration, ingestion, export, auth, and runtime provider/model switching.
- **20+ source connectors**: YouTube, Web, GitHub, Reddit, HackerNews, RSS, Podcast, Twitter/X, arXiv, S3, Google Workspace (Docs, Sheets, Slides), Microsoft 365 (SharePoint, OneDrive), Obsidian, Notion, Apple Notes, OneNote, Google Keep, Logseq, Zoom (OAuth), Teams, Google Meet.
- **Pluggable provider registry** supporting 15+ AI providers: OpenAI, Anthropic, Gemini, Ollama, Azure, Together, Fireworks, Cerebras, xAI, Bedrock, Vertex, Mistral, Cohere, AI21, HuggingFace, Qianfan, and LiteLLM.
- **Planning taxonomy classifier** for entity types: goal, requirement, risk, task, milestone, and other planning-specific categories.
- **Unified OAuth manager** (`planopticon auth`) with pre-built configs for Google, Dropbox, Zoom, Notion, GitHub, and Microsoft. Auth chain: saved token, OAuth PKCE, API key fallback.
- **Markdown document generator** producing 7 document types without an LLM: summary, meeting-notes, glossary, relationship-map, status-report, entity-index, csv.
- **Notes export** to Obsidian vaults (YAML frontmatter + wiki-links) and Notion-compatible markdown.
- **GitHub wiki generator** with direct push support.
- **PlanOpticonExchange** canonical JSON interchange format with merge and dedup.
- **Document ingestion pipeline** for PDF, Markdown, and plaintext sources.
- **Knowledge graph viewer** -- self-contained HTML file with inlined D3.js for browser-based graph exploration.
- **Graph query engine** with direct mode (stats, entities, neighbors, relationships) and agentic mode (natural language queries via LLM).
- **Progress callback system** for pipeline status reporting.

### Changed

- **SQLite replaces FalkorDB** for knowledge graph storage. Zero external dependencies -- no database server or additional packages required.
- **Default models** now target cheap/fast options: Claude Haiku, GPT-4o-mini, Gemini Flash.
- Output structure updated: `knowledge_graph.db` (SQLite) is now the primary graph file alongside the existing `knowledge_graph.json` export.

### Fixed

- 821+ tests passing across the full test suite.

## [0.3.0] - 2025-12-20

### Added

- FalkorDB integration for knowledge graph storage.
- Typed relationships and entity properties in graph data model.
- Relationship existence checks.

## [0.2.0] - 2025-10-15

### Added

- Batch video processing with merged knowledge graphs.
- Cloud sources: Google Drive and Dropbox shared folder fetching.
- Checkpoint/resume for interrupted pipelines.
- PDF report generation.

## [0.1.0] - 2025-08-01

### Added

- Initial release.
- Video analysis with multi-provider AI (OpenAI, Anthropic, Gemini, Ollama).
- Smart frame extraction with change detection.
- People frame filtering via OpenCV face detection.
- Diagram extraction and classification.
- Knowledge graph extraction (entities and relationships).
- Action item detection with assignees and deadlines.
- Markdown and HTML report output.
- Mermaid diagram generation.

[0.6.0]: https://github.com/ConflictHQ/PlanOpticon/compare/v0.5.0...v0.6.0
[0.4.0]: https://github.com/ConflictHQ/PlanOpticon/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ConflictHQ/PlanOpticon/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ConflictHQ/PlanOpticon/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ConflictHQ/PlanOpticon/releases/tag/v0.1.0
