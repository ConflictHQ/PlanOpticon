# PlanOpticon

Video analysis and knowledge extraction CLI. Processes recordings into structured knowledge graphs with entities, relationships, and insights.

## Knowledge Graph Query Skill

PlanOpticon can build and query knowledge graphs from video content. If you see `knowledge_graph.db` or `knowledge_graph.json` files in the workspace, you can query them to understand what was discussed.

### Auto-detection

Look for these files (checked automatically):
- `knowledge_graph.db` — FalkorDB binary graph (preferred)
- `knowledge_graph.json` — JSON export (fallback)

Common locations: project root, `results/`, `output/`, `knowledge-base/`.

### Quick commands

```bash
# Show graph stats (entity/relationship counts)
planopticon query

# List entities filtered by type
planopticon query "entities --type technology"
planopticon query "entities --type person"

# Search entities by name
planopticon query "entities --name python"

# See what connects to an entity
planopticon query "neighbors Alice"

# List relationships
planopticon query "relationships --source Alice"

# Natural language (requires API key)
planopticon query "What technologies were discussed?"
planopticon query "Who are the key people mentioned?"

# Output as JSON or Mermaid diagram
planopticon query --format json stats
planopticon query --format mermaid "neighbors Alice"

# Interactive REPL
planopticon query -I
```

### When to use

- **Direct mode** (`stats`, `entities`, `neighbors`, `relationships`): No API key needed. Fast, deterministic. Use for structured lookups.
- **Agentic mode** (natural language questions): Requires an API key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.). Use when the user asks open-ended questions about the content.

### Python API

```python
from video_processor.integrators.graph_query import GraphQueryEngine
from video_processor.integrators.graph_discovery import find_nearest_graph

path = find_nearest_graph()
engine = GraphQueryEngine.from_db_path(path)
result = engine.stats()
print(result.to_text())
```
