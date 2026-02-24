"""Query engine for PlanOpticon knowledge graphs."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from video_processor.integrators.graph_store import (
    GraphStore,
    InMemoryStore,
    create_store,
)

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Uniform wrapper for query results."""

    data: Any
    query_type: str  # "cypher", "filter", "agentic"
    raw_query: str = ""
    explanation: str = ""

    def to_text(self) -> str:
        """Human-readable text output."""
        lines = []
        if self.explanation:
            lines.append(self.explanation)
            lines.append("")

        if isinstance(self.data, dict):
            # Stats or single entity
            for key, value in self.data.items():
                if isinstance(value, dict):
                    lines.append(f"{key}:")
                    for k, v in value.items():
                        lines.append(f"  {k}: {v}")
                else:
                    lines.append(f"{key}: {value}")
        elif isinstance(self.data, list):
            if not self.data:
                lines.append("No results found.")
            for item in self.data:
                if isinstance(item, dict):
                    if "source" in item and "target" in item:
                        rtype = item.get("type", "related_to")
                        lines.append(f"  {item['source']} --[{rtype}]--> {item['target']}")
                    elif item.get("name") and item.get("type"):
                        descs = item.get("descriptions", [])
                        if isinstance(descs, set):
                            descs = list(descs)
                        desc_str = "; ".join(descs[:3]) if descs else ""
                        line = f"  [{item['type']}] {item['name']}"
                        if desc_str:
                            line += f" — {desc_str}"
                        lines.append(line)
                    else:
                        lines.append(f"  {item}")
                else:
                    lines.append(f"  {item}")
        else:
            lines.append(str(self.data))

        return "\n".join(lines)

    def to_json(self) -> str:
        """JSON string output."""
        payload = {
            "query_type": self.query_type,
            "raw_query": self.raw_query,
            "explanation": self.explanation,
            "data": self.data,
        }
        return json.dumps(payload, indent=2, default=str)

    def to_mermaid(self) -> str:
        """Mermaid diagram output from result data."""
        lines = ["graph LR"]
        seen_nodes = set()
        edges = []

        items = self.data if isinstance(self.data, list) else [self.data]

        for item in items:
            if not isinstance(item, dict):
                continue
            # Entity node
            if "name" in item and "type" in item:
                name = item["name"]
                if name not in seen_nodes:
                    safe_id = _mermaid_id(name)
                    safe_name = name.replace('"', "'")
                    ntype = item.get("type", "concept")
                    lines.append(f'    {safe_id}["{safe_name}"]:::{ntype}')
                    seen_nodes.add(name)
            # Relationship edge
            if "source" in item and "target" in item:
                src = item["source"]
                tgt = item["target"]
                rtype = item.get("type", "related_to")
                for n in (src, tgt):
                    if n not in seen_nodes:
                        safe_id = _mermaid_id(n)
                        lines.append(f'    {safe_id}["{n.replace(chr(34), chr(39))}"]')
                        seen_nodes.add(n)
                edges.append((src, tgt, rtype))

        for src, tgt, rtype in edges:
            lines.append(f'    {_mermaid_id(src)} -- "{rtype}" --> {_mermaid_id(tgt)}')

        lines.append("    classDef person fill:#f9d5e5,stroke:#333")
        lines.append("    classDef concept fill:#eeeeee,stroke:#333")
        lines.append("    classDef technology fill:#d5e5f9,stroke:#333")
        lines.append("    classDef organization fill:#f9e5d5,stroke:#333")

        return "\n".join(lines)


def _mermaid_id(name: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name)


class GraphQueryEngine:
    """Query engine with direct (no-LLM) and agentic (LLM) modes."""

    def __init__(self, store: GraphStore, provider_manager=None):
        self.store = store
        self.pm = provider_manager

    @classmethod
    def from_db_path(cls, path: Path, provider_manager=None) -> "GraphQueryEngine":
        """Open a .db file and create a query engine."""
        store = create_store(path)
        return cls(store, provider_manager)

    @classmethod
    def from_json_path(cls, path: Path, provider_manager=None) -> "GraphQueryEngine":
        """Load a .json knowledge graph file and create a query engine."""
        data = json.loads(Path(path).read_text())
        store = InMemoryStore()
        for node in data.get("nodes", []):
            store.merge_entity(
                node.get("name", ""),
                node.get("type", "concept"),
                node.get("descriptions", []),
            )
            for occ in node.get("occurrences", []):
                store.add_occurrence(
                    node.get("name", ""),
                    occ.get("source", ""),
                    occ.get("timestamp"),
                    occ.get("text"),
                )
        for rel in data.get("relationships", []):
            store.add_relationship(
                rel.get("source", ""),
                rel.get("target", ""),
                rel.get("type", "related_to"),
                content_source=rel.get("content_source"),
                timestamp=rel.get("timestamp"),
            )
        return cls(store, provider_manager)

    # ── Direct mode methods (no LLM required) ──

    def entities(
        self,
        name: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 50,
    ) -> QueryResult:
        """Filter entities by name substring and/or type."""
        all_entities = self.store.get_all_entities()
        results = []
        for e in all_entities:
            if name and name.lower() not in e.get("name", "").lower():
                continue
            if entity_type and entity_type.lower() != e.get("type", "").lower():
                continue
            results.append(e)
            if len(results) >= limit:
                break

        raw = f"entities(name={name!r}, entity_type={entity_type!r}, limit={limit})"
        return QueryResult(
            data=results,
            query_type="filter",
            raw_query=raw,
            explanation=f"Found {len(results)} entities",
        )

    def relationships(
        self,
        source: Optional[str] = None,
        target: Optional[str] = None,
        rel_type: Optional[str] = None,
        limit: int = 50,
    ) -> QueryResult:
        """Filter relationships by source, target, and/or type."""
        all_rels = self.store.get_all_relationships()
        results = []
        for r in all_rels:
            if source and source.lower() not in r.get("source", "").lower():
                continue
            if target and target.lower() not in r.get("target", "").lower():
                continue
            if rel_type and rel_type.lower() not in r.get("type", "").lower():
                continue
            results.append(r)
            if len(results) >= limit:
                break

        raw = f"relationships(source={source!r}, target={target!r}, rel_type={rel_type!r})"
        return QueryResult(
            data=results,
            query_type="filter",
            raw_query=raw,
            explanation=f"Found {len(results)} relationships",
        )

    def neighbors(self, entity_name: str, depth: int = 1) -> QueryResult:
        """Get an entity and its connected nodes (up to *depth* hops)."""
        entity = self.store.get_entity(entity_name)
        if not entity:
            return QueryResult(
                data=[],
                query_type="filter",
                raw_query=f"neighbors({entity_name!r}, depth={depth})",
                explanation=f"Entity '{entity_name}' not found",
            )

        visited = {entity_name.lower()}
        result_entities = [entity]
        result_rels = []
        frontier = {entity_name.lower()}

        all_rels = self.store.get_all_relationships()

        for _ in range(depth):
            next_frontier = set()
            for rel in all_rels:
                src_lower = rel["source"].lower()
                tgt_lower = rel["target"].lower()
                if src_lower in frontier or tgt_lower in frontier:
                    result_rels.append(rel)
                    for n in (src_lower, tgt_lower):
                        if n not in visited:
                            visited.add(n)
                            next_frontier.add(n)
                            e = self.store.get_entity(n)
                            if e:
                                result_entities.append(e)
            frontier = next_frontier

        # Combine entities + relationships into output
        combined = result_entities + result_rels
        return QueryResult(
            data=combined,
            query_type="filter",
            raw_query=f"neighbors({entity_name!r}, depth={depth})",
            explanation=(
                f"Found {len(result_entities)} entities and {len(result_rels)} relationships"
            ),
        )

    def stats(self) -> QueryResult:
        """Return entity count, relationship count, type breakdown."""
        all_entities = self.store.get_all_entities()
        type_breakdown = {}
        for e in all_entities:
            t = e.get("type", "concept")
            type_breakdown[t] = type_breakdown.get(t, 0) + 1

        data = {
            "entity_count": self.store.get_entity_count(),
            "relationship_count": self.store.get_relationship_count(),
            "entity_types": type_breakdown,
        }
        return QueryResult(
            data=data,
            query_type="filter",
            raw_query="stats()",
            explanation="Knowledge graph statistics",
        )

    def cypher(self, query: str) -> QueryResult:
        """Execute a raw Cypher query (FalkorDB only)."""
        result = self.store.raw_query(query)
        return QueryResult(
            data=result,
            query_type="cypher",
            raw_query=query,
            explanation=(
                f"Cypher query returned {len(result) if isinstance(result, list) else 1} rows"
            ),
        )

    # ── Agentic mode (requires LLM) ──

    def ask(self, question: str) -> QueryResult:
        """Answer a natural language question using LLM-guided query planning.

        The LLM picks from known direct-mode actions (never generates arbitrary code),
        the engine executes them, then the LLM synthesizes a natural language answer.
        """
        if not self.pm:
            return QueryResult(
                data=None,
                query_type="agentic",
                raw_query=question,
                explanation="Agentic mode requires a configured LLM provider. "
                "Pass --provider/--chat-model or set an API key.",
            )

        # Step 1: Ask LLM to generate a query plan
        stats = self.stats().data
        plan_prompt = (
            "You are a knowledge graph query planner. Given a user question and graph stats, "
            "choose ONE action to answer it.\n\n"
            f"Graph stats: {json.dumps(stats)}\n\n"
            "Available actions (pick exactly one):\n"
            '- {{"action": "entities", "name": "...", "entity_type": "..."}}\n'
            '- {{"action": "relationships", "source": "...", "target": "...", "rel_type": "..."}}\n'
            '- {{"action": "neighbors", "entity_name": "...", "depth": 1}}\n'
            '- {{"action": "stats"}}\n\n'
            f"User question: {question}\n\n"
            "Return ONLY a JSON object with the action. Omit optional fields you don't need."
        )

        try:
            plan_raw = self.pm.chat(
                [{"role": "user", "content": plan_prompt}],
                max_tokens=256,
                temperature=0.1,
            )
        except Exception as e:
            return QueryResult(
                data=None,
                query_type="agentic",
                raw_query=question,
                explanation=f"LLM query planning failed: {e}",
            )

        # Parse the plan
        plan = _parse_json(plan_raw)
        if not plan or "action" not in plan:
            return QueryResult(
                data=None,
                query_type="agentic",
                raw_query=question,
                explanation="Could not parse LLM query plan from response.",
            )

        # Step 2: Execute the planned action
        action = plan["action"]
        try:
            if action == "entities":
                result = self.entities(
                    name=plan.get("name"),
                    entity_type=plan.get("entity_type"),
                )
            elif action == "relationships":
                result = self.relationships(
                    source=plan.get("source"),
                    target=plan.get("target"),
                    rel_type=plan.get("rel_type"),
                )
            elif action == "neighbors":
                result = self.neighbors(
                    entity_name=plan.get("entity_name", ""),
                    depth=plan.get("depth", 1),
                )
            elif action == "stats":
                result = self.stats()
            else:
                return QueryResult(
                    data=None,
                    query_type="agentic",
                    raw_query=question,
                    explanation=f"Unknown action in plan: {action}",
                )
        except Exception as e:
            return QueryResult(
                data=None,
                query_type="agentic",
                raw_query=question,
                explanation=f"Action execution failed: {e}",
            )

        # Step 3: Synthesize a natural language answer
        synth_prompt = (
            "You are a helpful assistant answering questions about a knowledge graph.\n\n"
            f"User question: {question}\n\n"
            f"Query result:\n{result.to_text()}\n\n"
            "Provide a concise, natural language answer based on the data above."
        )

        try:
            answer = self.pm.chat(
                [{"role": "user", "content": synth_prompt}],
                max_tokens=1024,
                temperature=0.3,
            )
        except Exception as e:
            # Return the raw result if synthesis fails
            result.query_type = "agentic"
            result.explanation = f"LLM synthesis failed ({e}), showing raw results"
            return result

        return QueryResult(
            data=result.data,
            query_type="agentic",
            raw_query=question,
            explanation=answer.strip(),
        )


def _parse_json(text: str) -> Optional[Dict]:
    """Try to extract a JSON object from LLM output."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to find JSON between braces
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None
