# CLI Reference

## `planopticon analyze`

Analyze a single video and extract structured knowledge.

```bash
planopticon analyze [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-i`, `--input` | PATH | *required* | Input video file path |
| `-o`, `--output` | PATH | *required* | Output directory |
| `--depth` | `basic\|standard\|comprehensive` | `standard` | Processing depth |
| `--focus` | TEXT | all | Comma-separated focus areas |
| `--use-gpu` | FLAG | off | Enable GPU acceleration |
| `--sampling-rate` | FLOAT | 0.5 | Frame sampling rate (fps) |
| `--change-threshold` | FLOAT | 0.15 | Visual change threshold |
| `--periodic-capture` | FLOAT | 30.0 | Capture a frame every N seconds regardless of change (0 to disable) |
| `--title` | TEXT | auto | Report title |
| `-p`, `--provider` | `auto\|openai\|anthropic\|gemini` | `auto` | API provider |
| `--vision-model` | TEXT | auto | Override vision model |
| `--chat-model` | TEXT | auto | Override chat model |

---

## `planopticon batch`

Process a folder of videos in batch.

```bash
planopticon batch [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-i`, `--input-dir` | PATH | *required* | Directory containing videos |
| `-o`, `--output` | PATH | *required* | Output directory |
| `--depth` | `basic\|standard\|comprehensive` | `standard` | Processing depth |
| `--pattern` | TEXT | `*.mp4,*.mkv,*.avi,*.mov,*.webm` | File glob patterns |
| `--title` | TEXT | `Batch Processing Results` | Batch title |
| `-p`, `--provider` | `auto\|openai\|anthropic\|gemini` | `auto` | API provider |
| `--vision-model` | TEXT | auto | Override vision model |
| `--chat-model` | TEXT | auto | Override chat model |

---

## `planopticon list-models`

Discover and display available models from all configured providers.

```bash
planopticon list-models
```

No options. Queries each provider's API and displays models grouped by provider with capabilities.

---

## `planopticon clear-cache`

Clear API response cache.

```bash
planopticon clear-cache [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--cache-dir` | PATH | `$CACHE_DIR` | Path to cache directory |
| `--older-than` | INT | all | Clear entries older than N seconds |
| `--all` | FLAG | off | Clear all cache entries |

---

## Global options

| Option | Description |
|--------|-------------|
| `-v`, `--verbose` | Enable debug-level logging |
| `--version` | Show version and exit |
| `--help` | Show help and exit |
