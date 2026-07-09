# Knowledge Graphs

PlanOpticon builds structured knowledge graphs from video analyses, document ingestion, and other content sources. A knowledge graph captures **entities** (people, technologies, concepts, organizations) and the **relationships** between them, providing a queryable representation of everything discussed or presented in your source material.

---

## Storage

Knowledge graphs are stored as SQLite databases (`knowledge_graph.db`) using Python's built-in `sqlite3` module. This means:

- **Zero external dependencies.** No database server to install or manage.
- **Single-file portability.** Copy the `.db` file to share a knowledge graph.
- **WAL mode.** SQLite Write-Ahead Logging is enabled for concurrent read performance.
- **JSON fallback.** Knowledge graphs can also be saved as `knowledge_graph.json` for interoperability, though SQLite is preferred for performance and querying.

### Database Schema

The SQLite store uses the following tables:

| Table | Purpose |
|---|---|
| `entities` | Core entity records with name, type, descriptions, source, and arbitrary properties |
| `occurrences` | Where and when each entity was mentioned (source, timestamp, text snippet) |
| `relationships` | Directed edges between entities with type, content source, timestamp, and properties |
| `sources` | Registered content sources with provenance metadata (source type, title, path, URL, MIME type, ingestion timestamp) |
| `source_locations` | Links between sources and specific entities/relationships, with location details (timestamp, page, section, line range, text snippet) |

All entity lookups are case-insensitive (indexed on `name_lower`). Entities and relationships are indexed on their source and target fields for efficient traversal.

### Storage Backends

PlanOpticon supports two storage backends, selected automatically:

| Backend | When Used | Persistence |
|---|---|---|
| `SQLiteStore` | When a `db_path` is provided | Persistent on disk |
| `InMemoryStore` | When no path is given, or as fallback | In-memory only |

Both backends implement the same `GraphStore` abstract interface, so all query and manipulation code works identically regardless of backend.

```python
from video_processor.integrators.graph_store import create_store

# Persistent SQLite store
store = create_store("/path/to/knowledge_graph.db")

# In-memory store (for temporary operations)
store = create_store()
```

### Ecosystem Integration (Navegador)

PlanOpticon is the extraction layer in a two-layer knowledge topology: it emits
self-contained graph artifacts, and [Navegador](https://github.com/ConflictHQ/navegador)
maintains the shared, queryable super-graph.

The supported default is **file handoff**:

1. PlanOpticon writes `knowledge_graph.db` (SQLite) and `knowledge_graph.json`
   as part of its normal output — no extra configuration.
2. Navegador ingests those artifacts into its FalkorDB graph:

```bash
navegador planopticon ingest path/to/knowledge_graph.db
```

This keeps PlanOpticon dependency-free (the SQLite backend is stdlib only) and
works offline; the shared graph is Navegador's concern. A native FalkorDB/Redis
storage backend for PlanOpticon — writing straight to the super-graph instead of
handing off files — is an optional, lower-priority enhancement tracked in
[#134](https://github.com/ConflictHQ/PlanOpticon/issues/134).

---

## Entity Types

Entities extracted from content are assigned one of the following base types:

| Type | Description | Specificity Rank |
|---|---|---|
| `person` | People mentioned or participating | 3 (highest) |
| `technology` | Tools, languages, frameworks, platforms | 3 |
| `organization` | Companies, teams, departments | 2 |
| `time` | Dates, deadlines, time references | 1 |
| `diagram` | Visual diagrams extracted from video frames | 1 |
| `concept` | General concepts, topics, ideas (default) | 0 (lowest) |

The specificity rank is used during merge operations: when two entities are matched as duplicates, the more specific type wins (e.g., `technology` overrides `concept`).

### Planning Taxonomy

Beyond the base entity types, PlanOpticon includes a planning taxonomy for classifying entities into project-planning categories. The `TaxonomyClassifier` maps extracted entities into these types:

| Planning Type | Keywords Matched |
|---|---|
| `goal` | goal, objective, aim, target outcome |
| `requirement` | must, should, requirement, need, required |
| `constraint` | constraint, limitation, restrict, cannot, must not |
| `decision` | decided, decision, chose, selected, agreed |
| `risk` | risk, concern, worry, danger, threat |
| `assumption` | assume, assumption, expecting, presume |
| `dependency` | depends, dependency, relies on, prerequisite, blocked |
| `milestone` | milestone, deadline, deliverable, release, launch |
| `task` | task, todo, action item, work item, implement |
| `feature` | feature, capability, functionality |

Classification works in two stages:

1. **Heuristic classification.** Entity descriptions are scanned for the keywords listed above. First match wins.
2. **LLM refinement.** If an LLM provider is available, entities are sent to the LLM for more nuanced classification with priority assignment (`high`, `medium`, `low`). LLM results override heuristic results on conflicts.

Classified entities are used by planning agent skills (project_plan, prd, roadmap, task_breakdown) to produce targeted, context-aware artifacts.

---

## Relationship Types

Relationships are directed edges between entities. The `type` field is a free-text string determined by the LLM during extraction. Common relationship types include:

- `related_to` (default)
- `works_with`
- `uses`
- `depends_on`
- `proposed`
- `discussed_by`
- `employed_by`
- `collaborates_with`
- `expert_in`

### Typed Relationships

The `add_typed_relationship()` method creates edges with custom labels and optional properties, enabling richer graph semantics:

```python
store.add_typed_relationship(
    source="Authentication Service",
    target="PostgreSQL",
    edge_label="USES_SYSTEM",
    properties={"purpose": "user credential storage", "version": "15"},
)
```

### Relationship Checks

You can check whether a relationship exists between two entities:

```python
# Check for any relationship
store.has_relationship("Alice", "Kubernetes")

# Check for a specific relationship type
store.has_relationship("Alice", "Kubernetes", edge_label="expert_in")
```

---

## Building a Knowledge Graph

### From Video Analysis

The primary path for building a knowledge graph is through video analysis. When you run `planopticon analyze`, the pipeline extracts entities and relationships from:

- **Transcript segments** -- batched in groups of 10 for efficient API usage, with speaker identification
- **Diagram content** -- text extracted from visual diagrams detected in video frames

```bash
planopticon analyze -i meeting.mp4 -o results/
# Creates results/knowledge_graph.db
```

### From Document Ingestion

Documents (Markdown, PDF, DOCX) can be ingested directly into a knowledge graph:

```bash
# Ingest a single file
planopticon ingest -i requirements.pdf -o results/

# Ingest a directory recursively
planopticon ingest -i docs/ -o results/ --recursive

# Ingest into an existing knowledge graph
planopticon ingest -i notes.md --db results/knowledge_graph.db
```

### From Batch Processing

Multiple videos can be processed in batch mode, with all results merged into a single knowledge graph:

```bash
planopticon batch -i videos/ -o results/
```

### Programmatic Construction

```python
from video_processor.integrators.knowledge_graph import KnowledgeGraph

# Create a new knowledge graph with LLM extraction
from video_processor.providers.manager import ProviderManager
pm = ProviderManager()
kg = KnowledgeGraph(provider_manager=pm, db_path="knowledge_graph.db")

# Add content (entities and relationships are extracted by LLM)
kg.add_content(
    text="Alice proposed using Kubernetes for container orchestration.",
    source="meeting_notes",
    timestamp=120.5,
)

# Process a full transcript
kg.process_transcript(transcript_data, batch_size=10)

# Process diagram results
kg.process_diagrams(diagram_results)

# Save
kg.save("knowledge_graph.db")
```

---

## Merge and Deduplication

When combining knowledge graphs from multiple sources, PlanOpticon performs intelligent merge with deduplication.

### Fuzzy Name Matching

Entity names are compared using Python's `SequenceMatcher` with a threshold of 0.85. This means "Kubernetes" and "kubernetes" are matched exactly (case-insensitive), while "React.js" and "ReactJS" may be matched as duplicates if their similarity ratio meets the threshold.

### Type Conflict Resolution

When two entities match but have different types, the more specific type wins based on the specificity ranking:

| Scenario | Result |
|---|---|
| `concept` vs `technology` | `technology` wins (rank 3 > rank 0) |
| `person` vs `concept` | `person` wins (rank 3 > rank 0) |
| `organization` vs `concept` | `organization` wins (rank 2 > rank 0) |
| `person` vs `technology` | Keeps whichever was first (equal rank) |

### Provenance Tracking

Merged entities receive a `merged_from:<original_name>` description entry, preserving the audit trail of which entities were unified.

### Programmatic Merge

```python
from video_processor.integrators.knowledge_graph import KnowledgeGraph

# Load two knowledge graphs
kg1 = KnowledgeGraph(db_path="project_a.db")
kg2 = KnowledgeGraph(db_path="project_b.db")

# Merge kg2 into kg1
kg1.merge(kg2)

# Save the merged result
kg1.save("merged.db")
```

The merge operation also copies all registered sources and occurrences, so provenance information is preserved across merges.

---

## Querying

PlanOpticon provides two query modes: direct mode (no LLM required) and agentic mode (LLM-powered natural language).

### Direct Mode

Direct mode queries are fast, deterministic, and require no API key. They are the right choice for structured lookups.

#### Stats

Return entity count, relationship count, and entity type breakdown:

```bash
planopticon query
```

```python
engine.stats()
# QueryResult with data: {
#   "entity_count": 42,
#   "relationship_count": 87,
#   "entity_types": {"technology": 15, "person": 12, ...}
# }
```

#### Entities

Filter entities by name substring and/or type:

```bash
planopticon query "entities --type technology"
planopticon query "entities --name python"
```

```python
engine.entities(entity_type="technology")
engine.entities(name="python")
engine.entities(name="auth", entity_type="concept", limit=10)
```

All filtering is case-insensitive. Results are capped at 50 by default (configurable via `limit`).

#### Neighbors

Get an entity and all directly connected nodes and relationships:

```bash
planopticon query "neighbors Alice"
```

```python
engine.neighbors("Alice", depth=1)
```

The `depth` parameter controls how many hops to traverse (default 1). The result includes both entity objects and relationship objects.

#### Relationships

Filter relationships by source, target, and/or type:

```bash
planopticon query "relationships --source Alice"
```

```python
engine.relationships(source="Alice")
engine.relationships(target="Kubernetes", rel_type="uses")
```

#### Sources

List all registered content sources:

```python
engine.sources()
```

#### Provenance

Get all source locations for a specific entity, showing exactly where it was mentioned:

```python
engine.provenance("Kubernetes")
# Returns source locations with timestamps, pages, sections, and text snippets
```

#### Raw SQL

Execute arbitrary SQL against the SQLite backend (SQLite stores only):

```python
engine.sql("SELECT name, type FROM entities WHERE type = 'technology' ORDER BY name")
```

### Agentic Mode

Agentic mode accepts natural-language questions and uses the LLM to plan and execute queries. It requires a configured LLM provider.

```bash
planopticon query "What technologies were discussed?"
planopticon query "Who are the key people mentioned?"
planopticon query "What depends on the authentication service?"
```

The agentic query pipeline:

1. **Plan.** The LLM receives graph stats and available actions (entities, relationships, neighbors, stats). It selects exactly one action and its parameters.
2. **Execute.** The chosen action is run through the direct-mode engine.
3. **Synthesize.** The LLM receives the raw query results and the original question, then produces a concise natural-language answer.

This design ensures the LLM never generates arbitrary code -- it only selects from a fixed set of known query actions.

```bash
# Requires an API key
planopticon query "What technologies were discussed?" -p openai

# Use the interactive REPL for multiple queries
planopticon query -I
```

---

## Graph Query Engine Python API

The `GraphQueryEngine` class provides the programmatic interface for all query operations.

### Initialization

```python
from video_processor.integrators.graph_query import GraphQueryEngine
from video_processor.integrators.graph_discovery import find_nearest_graph

# From a .db file
path = find_nearest_graph()
engine = GraphQueryEngine.from_db_path(path)

# From a .json file
engine = GraphQueryEngine.from_json_path("knowledge_graph.json")

# With an LLM provider for agentic mode
from video_processor.providers.manager import ProviderManager
pm = ProviderManager()
engine = GraphQueryEngine.from_db_path(path, provider_manager=pm)
```

### QueryResult

All query methods return a `QueryResult` dataclass with multiple output formats:

```python
result = engine.stats()

# Human-readable text
print(result.to_text())

# JSON string
print(result.to_json())

# Mermaid diagram (for graph results)
result = engine.neighbors("Alice")
print(result.to_mermaid())
```

The `QueryResult` contains:

| Field | Type | Description |
|---|---|---|
| `data` | Any | The raw result data (dict, list, or scalar) |
| `query_type` | str | `"filter"` for direct mode, `"agentic"` for LLM mode, `"sql"` for raw SQL |
| `raw_query` | str | String representation of the executed query |
| `explanation` | str | Human-readable explanation or LLM-synthesized answer |

---

## The Self-Contained HTML Viewer

PlanOpticon includes a zero-dependency HTML knowledge graph viewer at `knowledge-base/viewer.html`. This file is fully self-contained -- it inlines D3.js and requires no build step, no server, and no internet connection.

To use it, open `viewer.html` in a browser. It will load and visualize a `knowledge_graph.json` file (place it in the same directory, or use the file picker in the viewer).

The viewer provides:

- Interactive force-directed graph layout
- Zoom and pan navigation
- Entity nodes colored by type
- Relationship edges with labels
- Click-to-focus on individual entities
- Entity detail panel showing descriptions and connections

This covers approximately 80% of graph exploration needs with zero infrastructure.

---

## KG Management Commands

The `planopticon kg` command group provides utilities for managing knowledge graph files.

### kg convert

Convert a knowledge graph between SQLite and JSON formats:

```bash
# SQLite to JSON
planopticon kg convert results/knowledge_graph.db output.json

# JSON to SQLite
planopticon kg convert knowledge_graph.json knowledge_graph.db
```

The output format is inferred from the destination file extension. Source and destination must be different formats.

### kg sync

Synchronize a `.db` and `.json` knowledge graph, updating the stale one:

```bash
# Auto-detect which is newer and sync
planopticon kg sync results/knowledge_graph.db

# Explicit JSON path
planopticon kg sync knowledge_graph.db knowledge_graph.json

# Force a specific direction
planopticon kg sync knowledge_graph.db knowledge_graph.json --direction db-to-json
planopticon kg sync knowledge_graph.db knowledge_graph.json --direction json-to-db
```

If `JSON_PATH` is omitted, the `.json` path is derived from the `.db` path (same name, different extension). In `auto` mode (the default), the newer file is used as the source.

### kg inspect

Show summary statistics for a knowledge graph file:

```bash
planopticon kg inspect results/knowledge_graph.db
```

Output:

```
File: results/knowledge_graph.db
Store: sqlite
Entities: 42
Relationships: 87
Entity types:
  technology: 15
  person: 12
  concept: 10
  organization: 5
```

Works with both `.db` and `.json` files.

### kg classify

Classify knowledge graph entities into planning taxonomy types:

```bash
# Heuristic + LLM classification
planopticon kg classify results/knowledge_graph.db

# Heuristic only (no API key needed)
planopticon kg classify results/knowledge_graph.db -p none

# JSON output
planopticon kg classify results/knowledge_graph.db --format json
```

Text output groups entities by planning type:

```
GOALS (3)
  - Improve system reliability [high]
    Must achieve 99.9% uptime
  - Reduce deployment time [medium]
    Automate the deployment pipeline

RISKS (2)
  - Data migration complexity [high]
    Legacy schema incompatibilities
  ...

TASKS (5)
  - Implement OAuth2 flow
    Set up authentication service
  ...
```

JSON output returns an array of `PlanningEntity` objects with `name`, `planning_type`, `priority`, `description`, and `source_entities` fields.

### kg from-exchange

Import a PlanOpticonExchange JSON file into a knowledge graph database:

```bash
# Import to default location (./knowledge_graph.db)
planopticon kg from-exchange exchange.json

# Import to a specific path
planopticon kg from-exchange exchange.json -o project.db
```

The PlanOpticonExchange format is a standardized interchange format that includes entities, relationships, and source records.

---

## Output Formats

Query results can be output in three formats:

### Text (default)

Human-readable format with entity types in brackets, relationship arrows, and indented details:

```
Found 15 entities
  [technology] Python -- General-purpose programming language
  [person] Alice -- Lead engineer on the project
  [concept] Microservices -- Architectural pattern discussed
```

### JSON

Full structured output including query metadata:

```bash
planopticon query --format json stats
```

```json
{
  "query_type": "filter",
  "raw_query": "stats()",
  "explanation": "Knowledge graph statistics",
  "data": {
    "entity_count": 42,
    "relationship_count": 87,
    "entity_types": {
      "technology": 15,
      "person": 12
    }
  }
}
```

### Mermaid

Graph results rendered as Mermaid diagram syntax, ready for embedding in markdown:

```bash
planopticon query --format mermaid "neighbors Alice"
```

```
graph LR
    Alice["Alice"]:::person
    Python["Python"]:::technology
    Kubernetes["Kubernetes"]:::technology
    Alice -- "expert_in" --> Kubernetes
    Alice -- "works_with" --> Python
    classDef person fill:#f9d5e5,stroke:#333
    classDef concept fill:#eeeeee,stroke:#333
    classDef technology fill:#d5e5f9,stroke:#333
    classDef organization fill:#f9e5d5,stroke:#333
```

The `KnowledgeGraph.generate_mermaid()` method also produces full-graph Mermaid diagrams, capped at the top 30 most-connected nodes by default.

---

## Auto-Discovery

PlanOpticon automatically locates knowledge graph files using the `find_nearest_graph()` function. The search order is:

1. **Current directory** -- check for `knowledge_graph.db` and `knowledge_graph.json`
2. **Common subdirectories** -- `results/`, `output/`, `knowledge-base/`
3. **Recursive downward walk** -- up to 4 levels deep, skipping hidden directories
4. **Parent directory walk** -- upward through the directory tree, checking each level and its common subdirectories

Within each search phase, `.db` files are preferred over `.json` files. Results are sorted by proximity (closest first).

```python
from video_processor.integrators.graph_discovery import (
    find_nearest_graph,
    find_knowledge_graphs,
    describe_graph,
)

# Find the single closest knowledge graph
path = find_nearest_graph()

# Find all knowledge graphs, sorted by proximity
paths = find_knowledge_graphs()

# Find graphs starting from a specific directory
paths = find_knowledge_graphs(start_dir="/path/to/project")

# Disable upward walking
paths = find_knowledge_graphs(walk_up=False)

# Get summary stats without loading the full graph
info = describe_graph(path)
# {"entity_count": 42, "relationship_count": 87,
#  "entity_types": {...}, "store_type": "sqlite"}
```

Auto-discovery is used by the Companion REPL, the `planopticon query` command, and the planning agent when no explicit `--kb` path is provided.
