"""Interactive planning companion REPL for PlanOpticon."""

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mkv", ".webm"}
DOC_EXTS = {".md", ".pdf", ".docx"}


class CompanionREPL:
    """Smart REPL with workspace awareness and KG querying."""

    def __init__(
        self,
        kb_paths: Optional[List[str]] = None,
        provider: str = "auto",
        chat_model: Optional[str] = None,
    ):
        self.kg = None
        self.query_engine = None
        self.agent = None
        self.provider_manager = None
        self._kb_paths = kb_paths or []
        self._provider_name = provider
        self._chat_model = chat_model
        self._videos: List[Path] = []
        self._docs: List[Path] = []
        self._kg_path: Optional[Path] = None

    def _discover(self) -> None:
        """Auto-discover workspace context."""
        # Discover knowledge graphs
        from video_processor.integrators.graph_discovery import (
            find_nearest_graph,
        )

        if self._kb_paths:
            # Use explicit paths
            self._kg_path = Path(self._kb_paths[0])
        else:
            self._kg_path = find_nearest_graph()

        if self._kg_path and self._kg_path.exists():
            self._load_kg(self._kg_path)

        # Scan for media and doc files in cwd
        cwd = Path.cwd()
        try:
            for f in sorted(cwd.iterdir()):
                if f.suffix.lower() in VIDEO_EXTS:
                    self._videos.append(f)
                elif f.suffix.lower() in DOC_EXTS:
                    self._docs.append(f)
        except PermissionError:
            pass

    def _load_kg(self, path: Path) -> None:
        """Load a knowledge graph from a file path."""
        from video_processor.integrators.graph_query import (
            GraphQueryEngine,
        )

        try:
            if path.suffix == ".json":
                self.query_engine = GraphQueryEngine.from_json_path(path)
            else:
                self.query_engine = GraphQueryEngine.from_db_path(path)
            self.kg = self.query_engine.store
        except Exception as exc:
            logger.debug("Failed to load KG at %s: %s", path, exc)

    def _init_provider(self) -> None:
        """Try to initialise an LLM provider."""
        try:
            from video_processor.providers.manager import (
                ProviderManager,
            )

            prov = None if self._provider_name == "auto" else self._provider_name
            self.provider_manager = ProviderManager(
                chat_model=self._chat_model,
                provider=prov,
            )
        except Exception:
            self.provider_manager = None

    def _init_agent(self) -> None:
        """Create a PlanningAgent if possible."""
        try:
            from video_processor.agent.agent_loop import (
                PlanningAgent,
            )
            from video_processor.agent.skills.base import (
                AgentContext,
            )

            ctx = AgentContext(
                knowledge_graph=self.kg,
                query_engine=self.query_engine,
                provider_manager=self.provider_manager,
            )
            self.agent = PlanningAgent(context=ctx)
        except Exception:
            self.agent = None

    def _welcome_banner(self) -> str:
        """Build the welcome banner text."""
        lines = [
            "",
            "  PlanOpticon Companion",
            "  Interactive planning REPL",
            "",
        ]

        if self._kg_path and self.query_engine:
            stats = self.query_engine.stats().data
            lines.append(
                f"  Knowledge graph: {self._kg_path.name}"
                f"  ({stats['entity_count']} entities,"
                f" {stats['relationship_count']} relationships)"
            )
        else:
            lines.append("  No knowledge graph loaded.")

        if self._videos:
            names = ", ".join(v.name for v in self._videos[:3])
            suffix = f" (+{len(self._videos) - 3} more)" if len(self._videos) > 3 else ""
            lines.append(f"  Videos: {names}{suffix}")

        if self._docs:
            names = ", ".join(d.name for d in self._docs[:3])
            suffix = f" (+{len(self._docs) - 3} more)" if len(self._docs) > 3 else ""
            lines.append(f"  Docs: {names}{suffix}")

        if self.provider_manager:
            prov = getattr(self.provider_manager, "provider", self._provider_name)
            model = self._chat_model or "default"
            lines.append(f"  LLM provider: {prov} (model: {model})")
        else:
            lines.append("  LLM provider: none")
        lines.append("")
        lines.append("  Type /help for commands, or ask a question.")
        lines.append("")
        return "\n".join(lines)

    # ── Command handlers ──

    def _cmd_help(self) -> str:
        lines = [
            "Available commands:",
            "  /help                  Show this help",
            "  /status                Workspace status",
            "  /skills                List available skills",
            "  /entities [--type T]   List KG entities",
            "  /search TERM           Search entities by name",
            "  /neighbors ENTITY      Show entity relationships",
            "  /export FORMAT         Export KG (markdown, obsidian, notion, csv)",
            "  /analyze PATH          Analyze a video/doc",
            "  /ingest PATH           Ingest a file into the KG",
            "  /auth SERVICE          Authenticate with a cloud service",
            "  /provider [NAME]       List or switch LLM provider",
            "  /model [NAME]          Show or switch chat model",
            "  /run SKILL             Run a skill by name",
            "  /plan                  Run project_plan skill",
            "  /prd                   Run PRD skill",
            "  /tasks                 Run task_breakdown skill",
            "  /quit, /exit           Exit companion",
            "",
            "Any other input is sent to the chat agent (requires LLM).",
        ]
        return "\n".join(lines)

    def _cmd_status(self) -> str:
        lines = ["Workspace status:"]
        if self._kg_path and self.query_engine:
            stats = self.query_engine.stats().data
            lines.append(
                f"  KG: {self._kg_path}"
                f" ({stats['entity_count']} entities,"
                f" {stats['relationship_count']} relationships)"
            )
            if stats.get("entity_types"):
                for t, c in sorted(
                    stats["entity_types"].items(),
                    key=lambda x: -x[1],
                ):
                    lines.append(f"    {t}: {c}")
        else:
            lines.append("  KG: not loaded")

        lines.append(f"  Videos: {len(self._videos)} found")
        lines.append(f"  Docs: {len(self._docs)} found")
        lines.append(f"  Provider: {'active' if self.provider_manager else 'none'}")
        return "\n".join(lines)

    def _cmd_skills(self) -> str:
        from video_processor.agent.skills.base import (
            list_skills,
        )

        skills = list_skills()
        if not skills:
            return "No skills registered."
        lines = ["Available skills:"]
        for s in skills:
            lines.append(f"  {s.name}: {s.description}")
        return "\n".join(lines)

    def _cmd_entities(self, args: str) -> str:
        if not self.query_engine:
            return "No knowledge graph loaded."
        entity_type = None
        parts = args.split()
        for i, part in enumerate(parts):
            if part == "--type" and i + 1 < len(parts):
                entity_type = parts[i + 1]
        result = self.query_engine.entities(
            entity_type=entity_type,
        )
        return result.to_text()

    def _cmd_search(self, term: str) -> str:
        if not self.query_engine:
            return "No knowledge graph loaded."
        term = term.strip()
        if not term:
            return "Usage: /search TERM"
        result = self.query_engine.entities(name=term)
        return result.to_text()

    def _cmd_neighbors(self, entity: str) -> str:
        if not self.query_engine:
            return "No knowledge graph loaded."
        entity = entity.strip()
        if not entity:
            return "Usage: /neighbors ENTITY"
        result = self.query_engine.neighbors(entity)
        return result.to_text()

    def _cmd_export(self, fmt: str) -> str:
        fmt = fmt.strip().lower()
        if not fmt:
            return "Usage: /export FORMAT (markdown, obsidian, notion, csv)"
        if not self._kg_path:
            return "No knowledge graph loaded."
        return (
            f"Export '{fmt}' requested. Use the CLI command:\n"
            f"  planopticon export {fmt} {self._kg_path}"
        )

    def _cmd_analyze(self, path_str: str) -> str:
        path_str = path_str.strip()
        if not path_str:
            return "Usage: /analyze PATH"
        p = Path(path_str)
        if not p.exists():
            return f"File not found: {path_str}"
        return f"Analyze requested for {p.name}. Use the CLI:\n  planopticon analyze -i {p}"

    def _cmd_ingest(self, path_str: str) -> str:
        path_str = path_str.strip()
        if not path_str:
            return "Usage: /ingest PATH"
        p = Path(path_str)
        if not p.exists():
            return f"File not found: {path_str}"
        return f"Ingest requested for {p.name}. Use the CLI:\n  planopticon ingest {p}"

    def _cmd_run_skill(self, skill_name: str) -> str:
        skill_name = skill_name.strip()
        if not skill_name:
            return "Usage: /run SKILL_NAME"
        from video_processor.agent.skills.base import (
            get_skill,
        )

        skill = get_skill(skill_name)
        if not skill:
            return f"Unknown skill: {skill_name}"
        if not self.agent:
            return "Agent not initialised (no LLM provider?)."
        if not skill.can_execute(self.agent.context):
            return f"Skill '{skill_name}' cannot execute in current context."
        try:
            artifact = skill.execute(self.agent.context)
            return f"--- {artifact.name} ({artifact.artifact_type}) ---\n{artifact.content}"
        except Exception as exc:
            return f"Skill execution failed: {exc}"

    def _cmd_auth(self, args: str) -> str:
        """Authenticate with a cloud service."""
        service = args.strip().lower()
        if not service:
            from video_processor.auth import KNOWN_CONFIGS

            services = ", ".join(sorted(KNOWN_CONFIGS.keys()))
            return f"Usage: /auth SERVICE\nAvailable: {services}"

        from video_processor.auth import get_auth_manager

        manager = get_auth_manager(service)
        if not manager:
            return f"Unknown service: {service}"

        result = manager.authenticate()
        if result.success:
            return f"{service.title()} authenticated ({result.method})"
        return f"{service.title()} auth failed: {result.error}"

    def _cmd_provider(self, args: str) -> str:
        """List available providers or switch to a specific one."""
        args = args.strip().lower()
        if not args or args == "list":
            lines = ["Available providers:"]
            known = [
                "openai",
                "anthropic",
                "gemini",
                "ollama",
                "azure",
                "together",
                "fireworks",
                "cerebras",
                "xai",
            ]
            import os

            key_map = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "gemini": "GEMINI_API_KEY",
                "azure": "AZURE_OPENAI_API_KEY",
                "together": "TOGETHER_API_KEY",
                "fireworks": "FIREWORKS_API_KEY",
                "cerebras": "CEREBRAS_API_KEY",
                "xai": "XAI_API_KEY",
            }
            current = getattr(self.provider_manager, "provider", self._provider_name)
            for name in known:
                env = key_map.get(name)
                has_key = bool(os.environ.get(env, "")) if env else None
                if name == "ollama":
                    status = "local"
                elif has_key:
                    status = "ready"
                else:
                    status = "no key"
                active = " (active)" if name == current else ""
                lines.append(f"  {name}: {status}{active}")
            lines.append(f"\nCurrent: {current or 'none'}")
            return "\n".join(lines)

        # Switch provider
        self._provider_name = args
        self._chat_model = None
        self._init_provider()
        self._init_agent()
        if self.provider_manager:
            return f"Switched to provider: {args}"
        return f"Failed to initialise provider: {args}"

    def _cmd_model(self, args: str) -> str:
        """Switch the chat model."""
        args = args.strip()
        if not args:
            current = self._chat_model or "default"
            return f"Current model: {current}\nUsage: /model MODEL_NAME"
        self._chat_model = args
        self._init_provider()
        self._init_agent()
        if self.provider_manager:
            return f"Switched to model: {args}"
        return f"Failed to initialise with model: {args}"

    def _cmd_chat(self, message: str) -> str:
        if not self.provider_manager or not self.agent:
            return (
                "Chat requires an LLM provider. Set one of:\n"
                "  OPENAI_API_KEY\n"
                "  ANTHROPIC_API_KEY\n"
                "  GEMINI_API_KEY\n"
                "Or pass --provider / --chat-model."
            )
        try:
            return self.agent.chat(message)
        except Exception as exc:
            return f"Chat error: {exc}"

    # ── Main dispatch ──

    def handle_input(self, line: str) -> str:
        """Process a single input line and return output."""
        line = line.strip()
        if not line:
            return ""

        if not line.startswith("/"):
            return self._cmd_chat(line)

        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit"):
            return "__QUIT__"
        if cmd == "/help":
            return self._cmd_help()
        if cmd == "/status":
            return self._cmd_status()
        if cmd == "/skills":
            return self._cmd_skills()
        if cmd == "/entities":
            return self._cmd_entities(args)
        if cmd == "/search":
            return self._cmd_search(args)
        if cmd == "/neighbors":
            return self._cmd_neighbors(args)
        if cmd == "/export":
            return self._cmd_export(args)
        if cmd == "/analyze":
            return self._cmd_analyze(args)
        if cmd == "/ingest":
            return self._cmd_ingest(args)
        if cmd == "/auth":
            return self._cmd_auth(args)
        if cmd == "/provider":
            return self._cmd_provider(args)
        if cmd == "/model":
            return self._cmd_model(args)
        if cmd == "/run":
            return self._cmd_run_skill(args)
        if cmd == "/plan":
            return self._cmd_run_skill("project_plan")
        if cmd == "/prd":
            return self._cmd_run_skill("prd")
        if cmd == "/tasks":
            return self._cmd_run_skill("task_breakdown")

        return f"Unknown command: {cmd}. Type /help for help."

    def run(self) -> None:
        """Main REPL loop."""
        self._discover()
        self._init_provider()
        self._init_agent()

        print(self._welcome_banner())

        while True:
            try:
                line = input("planopticon> ")
            except (KeyboardInterrupt, EOFError):
                print("\nBye.")
                break

            output = self.handle_input(line)
            if output == "__QUIT__":
                print("Bye.")
                break
            if output:
                print(output)
