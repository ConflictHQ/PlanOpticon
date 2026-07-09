# Export

PlanOpticon provides multiple ways to export knowledge graph data into formats suitable for documentation, note-taking, collaboration, and interchange. All export commands work offline from a `knowledge_graph.db` file -- no API key is needed for template-based exports.

## Overview of export options

| Format | Command | API Key | Description |
|--------|---------|---------|-------------|
| Markdown documents | `planopticon export markdown` | No | 7 document types: summary, meeting notes, glossary, and more |
| Obsidian vault | `planopticon export obsidian` | No | YAML frontmatter, `[[wiki-links]]`, tag pages, Map of Content |
| Notion-compatible | `planopticon export notion` | No | Callout blocks, CSV database for bulk import |
| PlanOpticonExchange JSON | `planopticon export exchange` | No | Canonical interchange format for merging and sharing |
| conflict-kg/v1 | `planopticon export conflict-kg` | No | Cross-tool graph interchange format (JSON or SQLite) |
| GitHub wiki | `planopticon wiki generate` | No | Home, Sidebar, entity pages, type indexes |
| GitHub wiki push | `planopticon wiki push` | Git auth | Push generated wiki to a GitHub repo |

## Markdown document generator

The markdown exporter produces structured documents from knowledge graph data using pure template-based generation. No LLM calls are made -- the output is deterministic and based entirely on the entities and relationships in the graph.

### CLI usage

```
planopticon export markdown DB_PATH [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `DB_PATH` | Path to a `knowledge_graph.db` file |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output` | `-o` | `./export` | Output directory |
| `--type` | | `all` | Document types to generate (repeatable). Choices: `summary`, `meeting-notes`, `glossary`, `relationship-map`, `status-report`, `entity-index`, `csv`, `all` |

**Examples:**

```bash
# Generate all document types
planopticon export markdown knowledge_graph.db

# Generate only summary and glossary
planopticon export markdown kg.db -o ./docs --type summary --type glossary

# Generate meeting notes and CSV
planopticon export markdown kg.db --type meeting-notes --type csv
```

### Document types

#### summary (Executive Summary)

A high-level overview of the knowledge graph. Contains:

- Total entity and relationship counts
- Entity breakdown by type (table with counts and example names)
- Key entities ranked by number of connections (top 10)
- Relationship type breakdown with counts

This is useful for getting a quick overview of what a knowledge base contains.

#### meeting-notes (Meeting Notes)

Formats knowledge graph data as structured meeting notes. Organizes entities into planning-relevant categories:

- **Discussion Topics**: Entities of type `concept`, `technology`, or `topic` with their descriptions
- **Participants**: Entities of type `person`
- **Decisions & Constraints**: Entities of type `decision` or `constraint`
- **Action Items**: Entities of type `goal`, `feature`, or `milestone`, shown as checkboxes. If an entity has an `assigned_to` or `owned_by` relationship, the owner is shown as `@name`
- **Open Questions / Loose Ends**: Entities with one or fewer relationships (excluding people), indicating topics that may need follow-up

Includes a generation timestamp.

#### glossary (Glossary)

An alphabetically sorted dictionary of all entities in the knowledge graph. Each entry shows:

- Entity name (bold)
- Entity type (italic, in parentheses)
- First description

Format:

```
**Entity Name** *(type)*
: Description text here.
```

#### relationship-map (Relationship Map)

A comprehensive view of all relationships in the graph, organized by relationship type. Each type gets its own section with a table of source-target pairs.

Also includes a **Mermaid diagram** of the top 20 most-connected entities, rendered as a `graph LR` flowchart with labeled edges. This diagram can be rendered natively in GitHub, GitLab, Obsidian, and many other Markdown viewers.

#### status-report (Status Report)

A project-oriented status report that highlights planning entities:

- **Overview**: Counts of entities, relationships, features, milestones, requirements, and risks/constraints
- **Milestones**: Entities of type `milestone` with descriptions
- **Features**: Table of entities of type `feature` with descriptions (truncated to 60 characters)
- **Risks & Constraints**: Entities of type `risk` or `constraint`

Includes a generation timestamp.

#### entity-index (Entity Index)

A master index of all entities grouped by type. Each type section lists entities alphabetically with their first description. Shows total entity count and number of types.

#### csv (CSV Export)

A CSV file suitable for spreadsheet import. Columns:

| Column | Description |
|--------|-------------|
| Name | Entity name |
| Type | Entity type |
| Description | First description |
| Related To | Semicolon-separated list of entities this entity has outgoing relationships to |
| Source | First occurrence source |

### Entity briefs

In addition to the selected document types, the `generate_all()` function automatically creates individual entity brief pages in an `entities/` subdirectory. Each brief contains:

- Entity name and type
- Summary (all descriptions)
- Outgoing relationships (table of target entities and relationship types)
- Incoming relationships (table of source entities and relationship types)
- Source occurrences with timestamps and context text

## Obsidian vault export

The Obsidian exporter creates a complete vault structure with YAML frontmatter, `[[wiki-links]]` for entity cross-references, and Obsidian-compatible metadata.

### CLI usage

```
planopticon export obsidian DB_PATH [OPTIONS]
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output` | `-o` | `./obsidian-vault` | Output vault directory |

**Example:**

```bash
planopticon export obsidian knowledge_graph.db -o ./my-vault
```

### Generated structure

```
my-vault/
  _Index.md              # Map of Content (MOC)
  Tag - Person.md        # One tag page per entity type
  Tag - Technology.md
  Tag - Concept.md
  Alice.md               # Individual entity notes
  Python.md
  Microservices.md
  ...
```

### Entity notes

Each entity gets a dedicated note with:

**YAML frontmatter:**

```yaml
---
type: technology
tags:
  - technology
aliases:
  - Python 3
  - CPython
date: 2026-03-07
---
```

The frontmatter includes:

- `type`: The entity type
- `tags`: Entity type as a tag (for Obsidian tag-based filtering)
- `aliases`: Any known aliases for the entity (if available)
- `date`: The export date

**Body content:**

- `# Entity Name` heading
- Description paragraphs
- `## Relationships` section with `[[wiki-links]]` to related entities:
    ```
    - **uses**: [[FastAPI]]
    - **depends_on**: [[PostgreSQL]]
    ```
- `## Referenced by` section with incoming relationships:
    ```
    - **implements** from [[Backend Service]]
    ```

### Index note (Map of Content)

The `_Index.md` file serves as a Map of Content (MOC), listing all entities grouped by type with `[[wiki-links]]`:

```markdown
---
type: index
tags:
  - MOC
date: 2026-03-07
---

# Index

**47** entities | **31** relationships

## Concept

- [[Microservices]]
- [[REST API]]

## Person

- [[Alice]]
- [[Bob]]
```

### Tag pages

One tag page is created per entity type (e.g., `Tag - Person.md`, `Tag - Technology.md`). Each page has frontmatter tagging it with the entity type and lists all entities of that type with descriptions.

## Notion-compatible markdown export

The Notion exporter creates Markdown files with Notion-style callout blocks and a CSV database file for bulk import into Notion.

### CLI usage

```
planopticon export notion DB_PATH [OPTIONS]
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output` | `-o` | `./notion-export` | Output directory |

**Example:**

```bash
planopticon export notion knowledge_graph.db -o ./notion-export
```

### Generated structure

```
notion-export/
  Overview.md              # Knowledge graph overview page
  entities_database.csv    # CSV for Notion database import
  Alice.md                 # Individual entity pages
  Python.md
  ...
```

### Entity pages

Each entity page uses Notion-style callout syntax for metadata:

```markdown
# Python

> :computer: **Type:** technology

## Description

A high-level programming language...

> :memo: **Properties**
> - **version:** 3.11
> - **paradigm:** multi-paradigm

## Relationships

| Target | Relationship |
|--------|-------------|
| FastAPI | uses |
| Django | framework_for |

## Referenced by

| Source | Relationship |
|--------|-------------|
| Backend Service | implements |
```

### CSV database

The `entities_database.csv` file contains all entities in a format suitable for Notion's CSV database import:

| Column | Description |
|--------|-------------|
| Name | Entity name |
| Type | Entity type |
| Description | First two descriptions, semicolon-separated |
| Related To | Comma-separated list of outgoing relationship targets |

### Overview page

The `Overview.md` page provides a summary with entity counts and a grouped listing of all entities by type.

## GitHub wiki generator

The wiki generator creates a complete set of GitHub wiki pages from a knowledge graph, including navigation (Home page and Sidebar) and cross-linked entity pages.

### CLI usage

**Generate wiki pages locally:**

```
planopticon wiki generate DB_PATH [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output` | `-o` | `./wiki` | Output directory for wiki pages |
| `--title` | | `Knowledge Base` | Wiki title (shown on Home page) |

**Push wiki pages to GitHub:**

```
planopticon wiki push WIKI_DIR REPO [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `WIKI_DIR` | Path to the directory containing generated wiki `.md` files |
| `REPO` | GitHub repository in `owner/repo` format |

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--message` | `-m` | `Update wiki` | Git commit message |

**Examples:**

```bash
# Generate wiki pages
planopticon wiki generate knowledge_graph.db -o ./wiki

# Generate with a custom title
planopticon wiki generate kg.db -o ./wiki --title "Project Wiki"

# Push to GitHub
planopticon wiki push ./wiki ConflictHQ/PlanOpticon

# Push with a custom commit message
planopticon wiki push ./wiki owner/repo -m "Add entity pages"
```

### Generated pages

The wiki generator creates the following pages:

| Page | Description |
|------|-------------|
| `Home.md` | Main wiki page with entity counts, type links, and artifact links |
| `_Sidebar.md` | Navigation sidebar with links to Home, entity type indexes, and artifacts |
| `{Type}.md` | One index page per entity type with a table of entities and descriptions |
| `{Entity}.md` | Individual entity pages with type, descriptions, relationships, and sources |

### Entity pages

Each entity page contains:

- Entity name as the top heading
- **Type** label
- **Descriptions** section (bullet list)
- **Relationships** table with wiki-style links to target entities
- **Referenced By** table with links to source entities
- **Sources** section listing occurrences with timestamps and context

All entity and type names are cross-linked using GitHub wiki-compatible links (`[Name](Sanitized-Name)`).

### Push behavior

The `wiki push` command:

1. Clones the existing GitHub wiki repository (`https://github.com/{repo}.wiki.git`).
2. If the wiki does not exist yet, initializes a new Git repository.
3. Copies all `.md` files from the wiki directory into the clone.
4. Commits the changes.
5. Pushes to the remote (tries `master` first, then `main`).

This requires Git authentication with push access to the repository. The wiki must be enabled in the GitHub repository settings.

## PlanOpticonExchange JSON format

The PlanOpticonExchange is the canonical interchange format for PlanOpticon data. Every command produces it, and every export adapter can consume it. It provides a structured, versioned JSON representation of a complete knowledge graph with project metadata.

### CLI usage

```
planopticon export exchange DB_PATH [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output` | `-o` | `./exchange.json` | Output JSON file path |
| `--name` | | `Untitled` | Project name for the exchange payload |
| `--description` | | (empty) | Project description |

**Examples:**

```bash
# Basic export
planopticon export exchange knowledge_graph.db

# With project metadata
planopticon export exchange kg.db -o exchange.json --name "My Project" --description "Sprint 3 analysis"
```

### Schema

The exchange format has the following top-level structure:

```json
{
  "version": "1.0",
  "project": {
    "name": "My Project",
    "description": "Sprint 3 analysis",
    "created_at": "2026-03-07T10:30:00.000000",
    "updated_at": "2026-03-07T10:30:00.000000",
    "tags": ["sprint-3", "backend"]
  },
  "entities": [
    {
      "name": "Python",
      "type": "technology",
      "descriptions": ["A high-level programming language"],
      "source": "transcript",
      "occurrences": [
        {
          "source": "meeting.mp4",
          "timestamp": "00:05:23",
          "text": "We should use Python for the backend"
        }
      ]
    }
  ],
  "relationships": [
    {
      "source": "Python",
      "target": "Backend Service",
      "type": "used_by",
      "content_source": "transcript:meeting.mp4",
      "timestamp": 323.0
    }
  ],
  "artifacts": [
    {
      "name": "Project Plan",
      "content": "# Project Plan\n\n...",
      "artifact_type": "project_plan",
      "format": "markdown",
      "metadata": {}
    }
  ],
  "sources": [
    {
      "source_id": "abc123",
      "source_type": "video",
      "title": "Sprint Planning Meeting",
      "path": "/recordings/meeting.mp4",
      "url": null,
      "mime_type": "video/mp4",
      "ingested_at": "2026-03-07T10:00:00.000000",
      "metadata": {}
    }
  ]
}
```

**Top-level fields:**

| Field | Type | Description |
|-------|------|-------------|
| `version` | `str` | Schema version (currently `"1.0"`) |
| `project` | `ProjectMeta` | Project-level metadata |
| `entities` | `List[Entity]` | Knowledge graph entities |
| `relationships` | `List[Relationship]` | Knowledge graph relationships |
| `artifacts` | `List[ArtifactMeta]` | Generated artifacts (plans, PRDs, etc.) |
| `sources` | `List[SourceRecord]` | Content source provenance records |

### Merging exchange files

The exchange format supports merging, with automatic deduplication:

- Entities are deduplicated by name
- Relationships are deduplicated by the tuple `(source, target, type)`
- Artifacts are deduplicated by name
- Sources are deduplicated by `source_id`

```python
from video_processor.exchange import PlanOpticonExchange

# Load two exchange files
ex1 = PlanOpticonExchange.from_file("sprint-1.json")
ex2 = PlanOpticonExchange.from_file("sprint-2.json")

# Merge ex2 into ex1
ex1.merge(ex2)

# Save the combined result
ex1.to_file("combined.json")
```

The `project.updated_at` timestamp is updated automatically on merge.

### Python API

**Create from a knowledge graph:**

```python
from video_processor.exchange import PlanOpticonExchange
from video_processor.integrators.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph(db_path="knowledge_graph.db")
kg_data = kg.to_dict()

exchange = PlanOpticonExchange.from_knowledge_graph(
    kg_data,
    project_name="My Project",
    project_description="Analysis of sprint planning meetings",
    tags=["planning", "backend"],
)
```

**Save and load:**

```python
# Save to file
exchange.to_file("exchange.json")

# Load from file
loaded = PlanOpticonExchange.from_file("exchange.json")
```

**Get JSON Schema:**

```python
schema = PlanOpticonExchange.json_schema()
```

This returns the full JSON Schema for validation and documentation purposes.

## conflict-kg/v1 format

`conflict-kg/v1` is the canonical knowledge-graph interchange format shared by
all Conflict tools (PlanOpticon, Navegador, portal viewers) — a graph exported
from any tool loads anywhere with no adapter. One schema, two encodings: JSON
for small and medium graphs, SQLite for large ones (the SQLite file is
Cloudflare D1-compatible for read-only portal queries).

### CLI usage

```
planopticon export conflict-kg DB_PATH [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output` | `-o` | `./conflict_kg.json` (or `.db`) | Output file path |
| `--sqlite` | | off | Emit the SQLite encoding instead of JSON |

**Examples:**

```bash
# JSON encoding
planopticon export conflict-kg knowledge_graph.db

# SQLite encoding for large graphs / D1
planopticon export conflict-kg knowledge_graph.db --sqlite -o graph.db
```

### Schema

```json
{
  "format": "conflict-kg/v1",
  "nodes": [
    { "id": "python", "name": "Python", "type": "technology", "props": {} }
  ],
  "edges": [
    { "source": "alice", "target": "python", "type": "uses", "props": {} }
  ]
}
```

- `id` is stable and unique — the entity's case-insensitive name, matching the
  store's identity key.
- Edges reference node `id`s (not names or prop dicts), so loaders are O(1).
- Everything beyond the core fields lives under `props` (descriptions and
  occurrences for nodes; `content_source` and `timestamp` for edges).

The SQLite encoding is the same contract as two tables:

```sql
CREATE TABLE nodes (id TEXT PRIMARY KEY, name TEXT, type TEXT, props JSON);
CREATE TABLE edges (source TEXT, target TEXT, type TEXT, props JSON);
CREATE INDEX idx_edges_source ON edges(source);
CREATE INDEX idx_edges_target ON edges(target);
```

The legacy `knowledge_graph.json` shape (`{nodes, relationships}`) is unchanged
and remains supported for existing consumers; new integrations should read
conflict-kg/v1.

## Python API for all exporters

### Markdown document generation

```python
from pathlib import Path
from video_processor.exporters.markdown import (
    generate_all,
    generate_executive_summary,
    generate_meeting_notes,
    generate_glossary,
    generate_relationship_map,
    generate_status_report,
    generate_entity_index,
    generate_csv_export,
    generate_entity_brief,
    DOCUMENT_TYPES,
)
from video_processor.integrators.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph(db_path=Path("knowledge_graph.db"))
kg_data = kg.to_dict()

# Generate all document types at once
created_files = generate_all(kg_data, Path("./export"))

# Generate specific document types
created_files = generate_all(
    kg_data,
    Path("./export"),
    doc_types=["summary", "glossary", "csv"],
)

# Generate individual documents (returns markdown string)
summary = generate_executive_summary(kg_data)
notes = generate_meeting_notes(kg_data, title="Sprint Planning")
glossary = generate_glossary(kg_data)
rel_map = generate_relationship_map(kg_data)
status = generate_status_report(kg_data, title="Q1 Status")
index = generate_entity_index(kg_data)
csv_text = generate_csv_export(kg_data)

# Generate a brief for a single entity
entity = kg_data["nodes"][0]
relationships = kg_data["relationships"]
brief = generate_entity_brief(entity, relationships)
```

### Obsidian export

```python
from pathlib import Path
from video_processor.agent.skills.notes_export import export_to_obsidian
from video_processor.integrators.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph(db_path=Path("knowledge_graph.db"))
kg_data = kg.to_dict()

created_files = export_to_obsidian(kg_data, Path("./obsidian-vault"))
print(f"Created {len(created_files)} files")
```

### Notion export

```python
from pathlib import Path
from video_processor.agent.skills.notes_export import export_to_notion_md
from video_processor.integrators.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph(db_path=Path("knowledge_graph.db"))
kg_data = kg.to_dict()

created_files = export_to_notion_md(kg_data, Path("./notion-export"))
```

### Wiki generation

```python
from pathlib import Path
from video_processor.agent.skills.wiki_generator import (
    generate_wiki,
    write_wiki,
    push_wiki,
)
from video_processor.integrators.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph(db_path=Path("knowledge_graph.db"))
kg_data = kg.to_dict()

# Generate pages as a dict of {filename: content}
pages = generate_wiki(kg_data, title="Project Wiki")

# Write to disk
written = write_wiki(pages, Path("./wiki"))

# Push to GitHub (requires git auth)
success = push_wiki(Path("./wiki"), "owner/repo", message="Update wiki")
```

## Companion REPL

Inside the interactive companion REPL, use the `/export` command:

```
> /export markdown
Export 'markdown' requested. Use the CLI command:
  planopticon export markdown ./knowledge_graph.db

> /export obsidian
Export 'obsidian' requested. Use the CLI command:
  planopticon export obsidian ./knowledge_graph.db
```

The REPL provides guidance on the CLI command to run; actual export is performed via the CLI.

## Common workflows

### Analyze videos and export to Obsidian

```bash
# Analyze meeting recordings
planopticon analyze meeting-1.mp4 -o ./results
planopticon analyze meeting-2.mp4 --db-path ./results/knowledge_graph.db

# Ingest supplementary docs
planopticon ingest ./specs/ --db-path ./results/knowledge_graph.db

# Export to Obsidian vault
planopticon export obsidian ./results/knowledge_graph.db -o ~/Obsidian/ProjectVault

# Open in Obsidian and explore the graph view
```

### Generate project documentation

```bash
# Generate all markdown documents
planopticon export markdown knowledge_graph.db -o ./docs

# The output includes:
#   docs/summary.md           - Executive summary
#   docs/meeting-notes.md     - Meeting notes format
#   docs/glossary.md          - Entity glossary
#   docs/relationship-map.md  - Relationships + Mermaid diagram
#   docs/status-report.md     - Project status report
#   docs/entity-index.md      - Master entity index
#   docs/csv.csv              - Spreadsheet-ready CSV
#   docs/entities/             - Individual entity briefs
```

### Publish a GitHub wiki

```bash
# Generate wiki pages
planopticon wiki generate knowledge_graph.db -o ./wiki --title "Project Knowledge Base"

# Review locally, then push
planopticon wiki push ./wiki ConflictHQ/my-project -m "Initial wiki from meeting analysis"
```

### Share data between projects

```bash
# Export from project A
planopticon export exchange ./project-a/knowledge_graph.db \
    -o project-a.json --name "Project A"

# Export from project B
planopticon export exchange ./project-b/knowledge_graph.db \
    -o project-b.json --name "Project B"

# Merge in Python
python -c "
from video_processor.exchange import PlanOpticonExchange
a = PlanOpticonExchange.from_file('project-a.json')
b = PlanOpticonExchange.from_file('project-b.json')
a.merge(b)
a.to_file('combined.json')
print(f'Combined: {len(a.entities)} entities, {len(a.relationships)} relationships')
"
```

### Export for spreadsheet analysis

```bash
# Generate just the CSV
planopticon export markdown knowledge_graph.db --type csv -o ./export

# The file export/csv.csv can be opened in Excel, Google Sheets, etc.
```

Alternatively, the Notion export includes an `entities_database.csv` that can be imported into any spreadsheet tool or Notion database.
