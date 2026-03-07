# CLI Reference

## Global options

These options are available on all commands.

| Option | Description |
|--------|-------------|
| `-v`, `--verbose` | Enable debug-level logging |
| `-C`, `--chat` | Enable chat mode (interactive follow-up after command completes) |
| `-I`, `--interactive` | Enable interactive REPL mode |
| `--version` | Show version and exit |
| `--help` | Show help and exit |

---

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
| `-p`, `--provider` | `auto\|openai\|anthropic\|gemini\|ollama` | `auto` | API provider |
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
| `-p`, `--provider` | `auto\|openai\|anthropic\|gemini\|ollama` | `auto` | API provider |
| `--vision-model` | TEXT | auto | Override vision model |
| `--chat-model` | TEXT | auto | Override chat model |
| `--source` | `local\|gdrive\|dropbox` | `local` | Video source |
| `--folder-id` | TEXT | none | Google Drive folder ID |
| `--folder-path` | TEXT | none | Cloud folder path |
| `--recursive/--no-recursive` | FLAG | recursive | Recurse into subfolders |

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

## `planopticon agent-analyze`

Agentic video analysis — adaptive, intelligent processing that adjusts depth and focus based on content.

```bash
planopticon agent-analyze [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-i`, `--input` | PATH | *required* | Input video file path |
| `-o`, `--output` | PATH | *required* | Output directory |
| `--depth` | `basic\|standard\|comprehensive` | `standard` | Initial processing depth (agent may adapt) |
| `--title` | TEXT | auto | Report title |
| `-p`, `--provider` | `auto\|openai\|anthropic\|gemini\|ollama` | `auto` | API provider |
| `--vision-model` | TEXT | auto | Override vision model |
| `--chat-model` | TEXT | auto | Override chat model |

---

## `planopticon companion`

Interactive knowledge base companion. Opens a REPL for conversational exploration of your knowledge base.

```bash
planopticon companion [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--kb` | PATH | auto-detect | Path to knowledge base directory |
| `-p`, `--provider` | TEXT | `auto` | AI provider |
| `--chat-model` | TEXT | auto | Override chat model |

**Examples:**

```bash
# Start companion with auto-detected knowledge base
planopticon companion

# Point to a specific knowledge base
planopticon companion --kb ./my-kb

# Use a specific provider
planopticon companion --kb ./kb --provider anthropic --chat-model claude-sonnet-4-20250514
```

---

## `planopticon agent`

Planning agent with adaptive analysis. Runs an agentic loop that reasons about your knowledge base, plans actions, and executes them.

```bash
planopticon agent [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--kb` | PATH | auto-detect | Path to knowledge base directory |
| `-I`, `--interactive` | FLAG | off | Interactive mode (ask before each action) |
| `--export` | PATH | none | Export agent results to a file |
| `-p`, `--provider` | TEXT | `auto` | AI provider |
| `--chat-model` | TEXT | auto | Override chat model |

**Examples:**

```bash
# Run the agent interactively
planopticon agent --kb ./kb --interactive

# Run agent and export results
planopticon agent --kb ./kb --export ./plan.md

# Use a specific model
planopticon agent --kb ./kb --provider openai --chat-model gpt-4o
```

---

## `planopticon query`

Query the knowledge graph directly or with natural language.

```bash
planopticon query [OPTIONS] [QUERY]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--db-path` | PATH | auto-detect | Path to knowledge graph database |
| `--mode` | `direct\|agentic` | auto | Query mode (direct for structured, agentic for natural language) |
| `--format` | `text\|json\|mermaid` | `text` | Output format |
| `-I`, `--interactive` | FLAG | off | Interactive REPL mode |

**Examples:**

```bash
# Show graph stats
planopticon query stats

# List entities by type
planopticon query "entities --type technology"
planopticon query "entities --type person"

# Find neighbors of an entity
planopticon query "neighbors Alice"

# List relationships
planopticon query "relationships --source Alice"

# Natural language query (requires API key)
planopticon query "What technologies were discussed?"

# Output as Mermaid diagram
planopticon query --format mermaid "neighbors ProjectX"

# Output as JSON
planopticon query --format json stats

# Interactive REPL
planopticon query -I
```

---

## `planopticon ingest`

Ingest documents and files into a knowledge graph.

```bash
planopticon ingest [OPTIONS] INPUT
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output` | PATH | `./knowledge-base` | Output directory for the knowledge base |
| `--db-path` | PATH | auto | Path to existing knowledge graph database to merge into |
| `--recursive` | FLAG | off | Recursively process directories |
| `-p`, `--provider` | TEXT | `auto` | AI provider |

**Examples:**

```bash
# Ingest a single file
planopticon ingest ./meeting-notes.md --output ./kb

# Ingest a directory recursively
planopticon ingest ./docs/ --output ./kb --recursive

# Merge into an existing knowledge graph
planopticon ingest ./new-notes/ --db-path ./kb/knowledge_graph.db --recursive
```

---

## `planopticon auth`

Authenticate with cloud services via OAuth or API keys.

```bash
planopticon auth SERVICE [OPTIONS]
```

| Argument | Values | Description |
|----------|--------|-------------|
| `SERVICE` | `google\|dropbox\|zoom\|notion\|github\|microsoft` | Cloud service to authenticate with |

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--logout` | FLAG | off | Remove stored credentials for the service |

**Examples:**

```bash
# Authenticate with Google (Drive, Meet, YouTube, etc.)
planopticon auth google

# Authenticate with Dropbox
planopticon auth dropbox

# Authenticate with Zoom (for recording access)
planopticon auth zoom

# Authenticate with Notion
planopticon auth notion

# Authenticate with GitHub
planopticon auth github

# Authenticate with Microsoft 365 (OneDrive, Teams, etc.)
planopticon auth microsoft

# Log out of a service
planopticon auth google --logout
```

---

## `planopticon gws`

Google Workspace commands. List, fetch, and ingest content from Google Workspace (Drive, Docs, Sheets, Slides, Meet).

### `planopticon gws list`

List available files and recordings from Google Workspace.

```bash
planopticon gws list [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--type` | `drive\|docs\|sheets\|slides\|meet` | all | Filter by content type |
| `--folder-id` | TEXT | none | Google Drive folder ID |
| `--limit` | INT | 50 | Maximum results to return |

### `planopticon gws fetch`

Download content from Google Workspace.

```bash
planopticon gws fetch [OPTIONS] RESOURCE_ID
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output` | PATH | `./downloads` | Output directory |
| `--format` | TEXT | auto | Export format (pdf, docx, etc.) |

### `planopticon gws ingest`

Ingest Google Workspace content directly into a knowledge graph.

```bash
planopticon gws ingest [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--folder-id` | TEXT | none | Google Drive folder ID |
| `--output` | PATH | `./knowledge-base` | Knowledge base output directory |
| `--recursive` | FLAG | off | Recurse into subfolders |

**Examples:**

```bash
# List all Google Workspace files
planopticon gws list

# List only Google Docs
planopticon gws list --type docs

# Fetch a specific file
planopticon gws fetch abc123def --output ./downloads

# Ingest an entire Drive folder into a knowledge base
planopticon gws ingest --folder-id abc123 --output ./kb --recursive
```

---

## `planopticon m365`

Microsoft 365 commands. List, fetch, and ingest content from Microsoft 365 (OneDrive, SharePoint, Teams, Outlook).

### `planopticon m365 list`

List available files and recordings from Microsoft 365.

```bash
planopticon m365 list [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--type` | `onedrive\|sharepoint\|teams\|outlook` | all | Filter by content type |
| `--site` | TEXT | none | SharePoint site name |
| `--limit` | INT | 50 | Maximum results to return |

### `planopticon m365 fetch`

Download content from Microsoft 365.

```bash
planopticon m365 fetch [OPTIONS] RESOURCE_ID
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output` | PATH | `./downloads` | Output directory |

### `planopticon m365 ingest`

Ingest Microsoft 365 content directly into a knowledge graph.

```bash
planopticon m365 ingest [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--site` | TEXT | none | SharePoint site name |
| `--path` | TEXT | `/` | Folder path in OneDrive/SharePoint |
| `--output` | PATH | `./knowledge-base` | Knowledge base output directory |
| `--recursive` | FLAG | off | Recurse into subfolders |

**Examples:**

```bash
# List all Microsoft 365 content
planopticon m365 list

# List only Teams recordings
planopticon m365 list --type teams

# Fetch a specific file
planopticon m365 fetch item-id-123 --output ./downloads

# Ingest SharePoint content
planopticon m365 ingest --site "Engineering" --path "/Shared Documents" --output ./kb --recursive
```

---

## `planopticon recordings`

List meeting recordings from video conferencing platforms.

### `planopticon recordings zoom-list`

List Zoom cloud recordings.

```bash
planopticon recordings zoom-list [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--from` | DATE | 30 days ago | Start date (YYYY-MM-DD) |
| `--to` | DATE | today | End date (YYYY-MM-DD) |
| `--limit` | INT | 50 | Maximum results |

### `planopticon recordings teams-list`

List Microsoft Teams meeting recordings.

```bash
planopticon recordings teams-list [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--from` | DATE | 30 days ago | Start date (YYYY-MM-DD) |
| `--to` | DATE | today | End date (YYYY-MM-DD) |
| `--limit` | INT | 50 | Maximum results |

### `planopticon recordings meet-list`

List Google Meet recordings.

```bash
planopticon recordings meet-list [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--from` | DATE | 30 days ago | Start date (YYYY-MM-DD) |
| `--to` | DATE | today | End date (YYYY-MM-DD) |
| `--limit` | INT | 50 | Maximum results |

**Examples:**

```bash
# List recent Zoom recordings
planopticon recordings zoom-list

# List Teams recordings from a specific date range
planopticon recordings teams-list --from 2026-01-01 --to 2026-02-01

# List Google Meet recordings
planopticon recordings meet-list --limit 10
```

---

## `planopticon export`

Export knowledge base content to various formats.

### `planopticon export markdown`

Export knowledge base as Markdown files.

```bash
planopticon export markdown [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--input` | PATH | auto-detect | Knowledge base path |
| `--output` | PATH | `./export` | Output directory |

### `planopticon export obsidian`

Export knowledge base as an Obsidian vault with wikilinks and graph metadata.

```bash
planopticon export obsidian [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--input` | PATH | auto-detect | Knowledge base path |
| `--output` | PATH | `./obsidian-vault` | Output vault directory |

### `planopticon export notion`

Export knowledge base to Notion.

```bash
planopticon export notion [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--input` | PATH | auto-detect | Knowledge base path |
| `--parent-page` | TEXT | none | Notion parent page ID |

### `planopticon export exchange`

Export knowledge base as PlanOpticon Exchange Format (JSON).

```bash
planopticon export exchange [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--input` | PATH | auto-detect | Knowledge base path |
| `--output` | PATH | `./exchange.json` | Output file path |

**Examples:**

```bash
# Export to Markdown
planopticon export markdown --input ./kb --output ./docs

# Export to Obsidian vault
planopticon export obsidian --input ./kb --output ~/Obsidian/PlanOpticon

# Export to Notion
planopticon export notion --input ./kb --parent-page abc123

# Export as exchange format for interoperability
planopticon export exchange --input ./kb --output ./export.json
```

---

## `planopticon wiki`

Generate and publish wiki documentation from your knowledge base.

### `planopticon wiki generate`

Generate a static wiki site from the knowledge base.

```bash
planopticon wiki generate [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--input` | PATH | auto-detect | Knowledge base path |
| `--output` | PATH | `./wiki` | Output directory |

### `planopticon wiki push`

Push a generated wiki to a remote target (e.g., GitHub Wiki, Confluence).

```bash
planopticon wiki push [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--input` | PATH | `./wiki` | Wiki directory to push |
| `--target` | TEXT | *required* | Push target (e.g., `github://org/repo`, `confluence://space`) |

**Examples:**

```bash
# Generate a wiki from the knowledge base
planopticon wiki generate --input ./kb --output ./wiki

# Push wiki to GitHub
planopticon wiki push --input ./wiki --target "github://ConflictHQ/project-wiki"
```

---

## `planopticon kg`

Knowledge graph management commands.

### `planopticon kg convert`

Convert a knowledge graph between formats.

```bash
planopticon kg convert [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--input` | PATH | *required* | Input knowledge graph file |
| `--output` | PATH | *required* | Output file path |
| `--format` | `json\|db\|graphml\|csv` | auto (from extension) | Target format |

### `planopticon kg sync`

Synchronize two knowledge graphs (merge new data).

```bash
planopticon kg sync [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--source` | PATH | *required* | Source knowledge graph |
| `--target` | PATH | *required* | Target knowledge graph to merge into |

### `planopticon kg inspect`

Inspect a knowledge graph and display statistics.

```bash
planopticon kg inspect [OPTIONS] [PATH]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `PATH` | PATH | auto-detect | Knowledge graph file |

### `planopticon kg classify`

Classify and tag entities in a knowledge graph.

```bash
planopticon kg classify [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--db-path` | PATH | auto-detect | Knowledge graph database |
| `-p`, `--provider` | TEXT | `auto` | AI provider for classification |

### `planopticon kg from-exchange`

Import a knowledge graph from PlanOpticon Exchange Format.

```bash
planopticon kg from-exchange [OPTIONS] INPUT
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `INPUT` | PATH | *required* | Exchange format JSON file |
| `--output` | PATH | `./knowledge-base` | Output knowledge base directory |

**Examples:**

```bash
# Convert JSON knowledge graph to FalkorDB format
planopticon kg convert --input ./kg.json --output ./kg.db

# Merge two knowledge graphs
planopticon kg sync --source ./new-kg.db --target ./main-kg.db

# Inspect a knowledge graph
planopticon kg inspect ./knowledge_graph.db

# Classify entities with AI
planopticon kg classify --db-path ./kg.db --provider anthropic

# Import from exchange format
planopticon kg from-exchange ./export.json --output ./kb
```
