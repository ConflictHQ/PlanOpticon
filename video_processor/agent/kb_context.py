"""Knowledge base context manager for loading and merging knowledge graphs."""

import json
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class KBContext:
    """Load and merge multiple knowledge graphs into a unified context."""

    def __init__(self):
        self._sources: List[Path] = []
        self._kg = None  # KnowledgeGraph instance
        self._engine = None  # GraphQueryEngine instance

    def add_source(self, path) -> None:
        """Add a knowledge graph source (.db or .json file, or directory to search)."""
        path = Path(path).resolve()
        if path.is_dir():
            from video_processor.integrators.graph_discovery import find_knowledge_graphs

            graphs = find_knowledge_graphs(path)
            self._sources.extend(graphs)
        elif path.is_file():
            self._sources.append(path)
        else:
            raise FileNotFoundError(f"Not found: {path}")

    def load(self, provider_manager=None) -> "KBContext":
        """Load and merge all added sources into a single knowledge graph."""
        from video_processor.integrators.graph_query import GraphQueryEngine
        from video_processor.integrators.knowledge_graph import KnowledgeGraph

        self._kg = KnowledgeGraph(provider_manager=provider_manager)

        for source_path in self._sources:
            if source_path.suffix == ".db":
                other = KnowledgeGraph(db_path=source_path)
                self._kg.merge(other)
            elif source_path.suffix == ".json":
                data = json.loads(source_path.read_text())
                other = KnowledgeGraph.from_dict(data)
                self._kg.merge(other)

        self._engine = GraphQueryEngine(self._kg._store, provider_manager=provider_manager)
        return self

    @property
    def knowledge_graph(self):
        """Return the merged KnowledgeGraph, or None if not loaded."""
        if not self._kg:
            raise RuntimeError("Call load() first")
        return self._kg

    @property
    def query_engine(self):
        """Return the GraphQueryEngine, or None if not loaded."""
        if not self._engine:
            raise RuntimeError("Call load() first")
        return self._engine

    @property
    def sources(self) -> List[Path]:
        """Return the list of source paths."""
        return list(self._sources)

    def summary(self) -> str:
        """Generate a brief summary of the loaded knowledge base."""
        if not self._kg:
            return "No knowledge base loaded."

        stats = self._engine.stats().data
        lines = [
            f"Knowledge base: {len(self._sources)} source(s)",
            f"  Entities: {stats['entity_count']}",
            f"  Relationships: {stats['relationship_count']}",
        ]
        if stats.get("entity_types"):
            lines.append("  Entity types:")
            for t, count in sorted(stats["entity_types"].items(), key=lambda x: -x[1]):
                lines.append(f"    {t}: {count}")
        return "\n".join(lines)

    @classmethod
    def auto_discover(cls, start_dir: Optional[Path] = None, provider_manager=None) -> "KBContext":
        """Create a KBContext by auto-discovering knowledge graphs near start_dir."""
        from video_processor.integrators.graph_discovery import find_knowledge_graphs

        ctx = cls()
        graphs = find_knowledge_graphs(start_dir)
        for g in graphs:
            ctx._sources.append(g)
        if ctx._sources:
            ctx.load(provider_manager=provider_manager)
        return ctx
