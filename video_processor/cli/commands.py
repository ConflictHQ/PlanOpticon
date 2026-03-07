"""Command-line interface for PlanOpticon."""

import json
import logging
import os
import sys
from pathlib import Path

import click
import colorlog
from tqdm import tqdm


def setup_logging(verbose: bool = False) -> None:
    """Set up logging with color formatting."""
    log_level = logging.DEBUG if verbose else logging.INFO
    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)
    root_logger.addHandler(console_handler)


@click.group(invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.version_option("0.4.0", prog_name="PlanOpticon")
@click.pass_context
def cli(ctx, verbose):
    """PlanOpticon - Comprehensive Video Analysis & Knowledge Extraction Tool."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)

    if ctx.invoked_subcommand is None:
        _interactive_menu(ctx)


@cli.command()
@click.option(
    "--input", "-i", required=True, type=click.Path(exists=True), help="Input video file path"
)
@click.option("--output", "-o", required=True, type=click.Path(), help="Output directory")
@click.option(
    "--depth",
    type=click.Choice(["basic", "standard", "comprehensive"]),
    default="standard",
    help="Processing depth",
)
@click.option(
    "--focus", type=str, help='Comma-separated focus areas (e.g., "diagrams,action-items")'
)
@click.option("--use-gpu", is_flag=True, help="Enable GPU acceleration if available")
@click.option("--sampling-rate", type=float, default=0.5, help="Frame sampling rate")
@click.option("--change-threshold", type=float, default=0.15, help="Visual change threshold")
@click.option(
    "--periodic-capture",
    type=float,
    default=30.0,
    help="Capture a frame every N seconds regardless of change (0 to disable)",
)
@click.option("--title", type=str, help="Title for the analysis report")
@click.option(
    "--provider",
    "-p",
    type=click.Choice(
        [
            "auto",
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
    ),
    default="auto",
    help="API provider",
)
@click.option("--vision-model", type=str, default=None, help="Override model for vision tasks")
@click.option("--chat-model", type=str, default=None, help="Override model for LLM/chat tasks")
@click.option(
    "--output-format",
    type=click.Choice(["default", "json"]),
    default="default",
    help="Output format: default (files + summary) or json (structured JSON to stdout)",
)
@click.option(
    "--templates-dir",
    type=click.Path(exists=True),
    default=None,
    help="Directory with custom prompt template .txt files",
)
@click.option(
    "--speakers",
    type=str,
    default=None,
    help='Comma-separated speaker names for diarization hints (e.g., "Alice,Bob,Carol")',
)
@click.pass_context
def analyze(
    ctx,
    input,
    output,
    depth,
    focus,
    use_gpu,
    sampling_rate,
    change_threshold,
    periodic_capture,
    title,
    provider,
    vision_model,
    chat_model,
    output_format,
    templates_dir,
    speakers,
):
    """Analyze a single video and extract structured knowledge."""
    from video_processor.pipeline import process_single_video
    from video_processor.providers.manager import ProviderManager

    focus_areas = [a.strip().lower() for a in focus.split(",")] if focus else []
    speaker_hints = [s.strip() for s in speakers.split(",")] if speakers else None
    prov = None if provider == "auto" else provider

    pm = ProviderManager(
        vision_model=vision_model,
        chat_model=chat_model,
        provider=prov,
    )

    if templates_dir:
        from video_processor.utils.prompt_templates import PromptTemplate

        pm.prompt_templates = PromptTemplate(templates_dir=templates_dir)

    try:
        manifest = process_single_video(
            input_path=input,
            output_dir=output,
            provider_manager=pm,
            depth=depth,
            focus_areas=focus_areas,
            sampling_rate=sampling_rate,
            change_threshold=change_threshold,
            periodic_capture_seconds=periodic_capture,
            use_gpu=use_gpu,
            title=title,
            speaker_hints=speaker_hints,
        )
        if output_format == "json":
            click.echo(json.dumps(manifest.model_dump(), indent=2, default=str))
        else:
            click.echo(pm.usage.format_summary())
            click.echo(f"\n  Results: {output}/manifest.json")
    except Exception as e:
        logging.error(f"Error: {e}")
        if output_format == "json":
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(pm.usage.format_summary())
        if ctx.obj["verbose"]:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option(
    "--input-dir", "-i", type=click.Path(), default=None, help="Local directory of videos"
)
@click.option("--output", "-o", required=True, type=click.Path(), help="Output directory")
@click.option(
    "--depth",
    type=click.Choice(["basic", "standard", "comprehensive"]),
    default="standard",
    help="Processing depth",
)
@click.option(
    "--pattern",
    type=str,
    default="*.mp4,*.mkv,*.avi,*.mov,*.webm",
    help="File glob patterns (comma-separated)",
)
@click.option("--title", type=str, default="Batch Processing Results", help="Batch title")
@click.option(
    "--provider",
    "-p",
    type=click.Choice(
        [
            "auto",
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
    ),
    default="auto",
    help="API provider",
)
@click.option("--vision-model", type=str, default=None, help="Override model for vision tasks")
@click.option("--chat-model", type=str, default=None, help="Override model for LLM/chat tasks")
@click.option(
    "--source",
    type=click.Choice(["local", "gdrive", "dropbox"]),
    default="local",
    help="Video source (local directory, Google Drive, or Dropbox)",
)
@click.option("--folder-id", type=str, default=None, help="Google Drive folder ID")
@click.option("--folder-path", type=str, default=None, help="Cloud folder path")
@click.option(
    "--recursive/--no-recursive", default=True, help="Recurse into subfolders (default: recursive)"
)
@click.pass_context
def batch(
    ctx,
    input_dir,
    output,
    depth,
    pattern,
    title,
    provider,
    vision_model,
    chat_model,
    source,
    folder_id,
    folder_path,
    recursive,
):
    """Process a folder of videos in batch."""
    from video_processor.integrators.knowledge_graph import KnowledgeGraph
    from video_processor.integrators.plan_generator import PlanGenerator
    from video_processor.models import BatchManifest, BatchVideoEntry
    from video_processor.output_structure import (
        create_batch_output_dirs,
        write_batch_manifest,
    )
    from video_processor.pipeline import process_single_video
    from video_processor.providers.manager import ProviderManager

    prov = None if provider == "auto" else provider
    pm = ProviderManager(vision_model=vision_model, chat_model=chat_model, provider=prov)
    patterns = [p.strip() for p in pattern.split(",")]

    # Handle cloud sources
    if source != "local":
        download_dir = Path(output) / "_downloads"
        download_dir.mkdir(parents=True, exist_ok=True)

        if source == "gdrive":
            from video_processor.sources.google_drive import GoogleDriveSource

            cloud = GoogleDriveSource()
            if not cloud.authenticate():
                logging.error("Google Drive authentication failed")
                sys.exit(1)
            cloud_files = cloud.list_videos(
                folder_id=folder_id, folder_path=folder_path, patterns=patterns, recursive=recursive
            )
            cloud.download_all(cloud_files, download_dir)
        elif source == "dropbox":
            from video_processor.sources.dropbox_source import DropboxSource

            cloud = DropboxSource()
            if not cloud.authenticate():
                logging.error("Dropbox authentication failed")
                sys.exit(1)
            cloud_files = cloud.list_videos(folder_path=folder_path, patterns=patterns)
            cloud.download_all(cloud_files, download_dir)
        else:
            logging.error(f"Unknown source: {source}")
            sys.exit(1)

        input_dir = download_dir
    else:
        if not input_dir:
            logging.error("--input-dir is required for local source")
            sys.exit(1)
        input_dir = Path(input_dir)

    # Find videos (rglob for recursive, glob for flat)
    videos = []
    glob_fn = input_dir.rglob if recursive else input_dir.glob
    for pat in patterns:
        videos.extend(sorted(glob_fn(pat)))
    videos = sorted(set(videos))

    if not videos:
        logging.error(f"No videos found in {input_dir} matching {pattern}")
        sys.exit(1)

    logging.info(f"Found {len(videos)} videos to process")

    dirs = create_batch_output_dirs(output, title)
    manifests = []
    entries = []
    merged_kg_db = Path(output) / "knowledge_graph.db"
    merged_kg = KnowledgeGraph(db_path=merged_kg_db)

    for idx, video_path in enumerate(tqdm(videos, desc="Batch processing", unit="video")):
        video_name = video_path.stem
        video_output = dirs["videos"] / video_name
        logging.info(f"Processing video {idx + 1}/{len(videos)}: {video_path.name}")

        entry = BatchVideoEntry(
            video_name=video_name,
            manifest_path=f"videos/{video_name}/manifest.json",
        )

        try:
            manifest = process_single_video(
                input_path=video_path,
                output_dir=video_output,
                provider_manager=pm,
                depth=depth,
                title=f"Analysis of {video_name}",
            )
            entry.status = "completed"
            entry.diagrams_count = len(manifest.diagrams)
            entry.action_items_count = len(manifest.action_items)
            entry.key_points_count = len(manifest.key_points)
            entry.duration_seconds = manifest.video.duration_seconds
            manifests.append(manifest)

            # Merge knowledge graph (prefer .db, fall back to .json)
            kg_db = video_output / "results" / "knowledge_graph.db"
            kg_json = video_output / "results" / "knowledge_graph.json"
            if kg_db.exists():
                video_kg = KnowledgeGraph(db_path=kg_db)
                merged_kg.merge(video_kg)
            elif kg_json.exists():
                kg_data = json.loads(kg_json.read_text())
                video_kg = KnowledgeGraph.from_dict(kg_data)
                merged_kg.merge(video_kg)

        except Exception as e:
            logging.error(f"Failed to process {video_path.name}: {e}")
            entry.status = "failed"
            entry.error = str(e)
            if ctx.obj["verbose"]:
                import traceback

                traceback.print_exc()

        entries.append(entry)

    # Save merged knowledge graph (SQLite is primary, JSON is export)
    merged_kg.save(Path(output) / "knowledge_graph.json")

    # Generate batch summary
    plan_gen = PlanGenerator(provider_manager=pm, knowledge_graph=merged_kg)
    summary_path = Path(output) / "batch_summary.md"
    plan_gen.generate_batch_summary(
        manifests=manifests,
        kg=merged_kg,
        title=title,
        output_path=summary_path,
    )

    # Write batch manifest
    batch_manifest = BatchManifest(
        title=title,
        total_videos=len(videos),
        completed_videos=sum(1 for e in entries if e.status == "completed"),
        failed_videos=sum(1 for e in entries if e.status == "failed"),
        total_diagrams=sum(e.diagrams_count for e in entries),
        total_action_items=sum(e.action_items_count for e in entries),
        total_key_points=sum(e.key_points_count for e in entries),
        videos=entries,
        batch_summary_md="batch_summary.md",
        merged_knowledge_graph_json="knowledge_graph.json",
        merged_knowledge_graph_db="knowledge_graph.db",
    )
    write_batch_manifest(batch_manifest, output)
    click.echo(pm.usage.format_summary())
    click.echo(
        f"\n  Batch complete: {batch_manifest.completed_videos}"
        f"/{batch_manifest.total_videos} succeeded"
    )
    click.echo(f"  Results: {output}/batch_manifest.json")


@cli.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option(
    "--output", "-o", type=click.Path(), default=None, help="Output directory for knowledge graph"
)
@click.option(
    "--db-path", type=click.Path(), default=None, help="Existing knowledge_graph.db to add to"
)
@click.option("--recursive/--no-recursive", "-r", default=True, help="Recurse into subdirectories")
@click.option(
    "--provider",
    "-p",
    type=click.Choice(
        [
            "auto",
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
    ),
    default="auto",
    help="API provider",
)
@click.option("--chat-model", type=str, default=None, help="Override model for LLM/chat tasks")
@click.pass_context
def ingest(ctx, input_path, output, db_path, recursive, provider, chat_model):
    """Ingest documents into a knowledge graph.

    Supports: .md, .txt, .pdf (with pymupdf or pdfplumber installed)

    Examples:

        planopticon ingest spec.md

        planopticon ingest ./docs/ -o ./output

        planopticon ingest report.pdf --db-path existing.db
    """
    from video_processor.integrators.knowledge_graph import KnowledgeGraph
    from video_processor.processors import list_supported_extensions
    from video_processor.processors.ingest import ingest_directory, ingest_file
    from video_processor.providers.manager import ProviderManager

    input_path = Path(input_path)
    prov = None if provider == "auto" else provider
    pm = ProviderManager(chat_model=chat_model, provider=prov)

    # Determine DB path
    if db_path:
        kg_path = Path(db_path)
    elif output:
        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        kg_path = out_dir / "knowledge_graph.db"
    else:
        kg_path = Path.cwd() / "knowledge_graph.db"

    kg_path.parent.mkdir(parents=True, exist_ok=True)

    click.echo(f"Knowledge graph: {kg_path}")
    kg = KnowledgeGraph(provider_manager=pm, db_path=kg_path)

    total_files = 0
    total_chunks = 0

    try:
        if input_path.is_file():
            count = ingest_file(input_path, kg)
            total_files = 1
            total_chunks = count
            click.echo(f"  {input_path.name}: {count} chunks")
        elif input_path.is_dir():
            results = ingest_directory(input_path, kg, recursive=recursive)
            total_files = len(results)
            total_chunks = sum(results.values())
            for fpath, count in results.items():
                click.echo(f"  {Path(fpath).name}: {count} chunks")
        else:
            click.echo(f"Error: {input_path} is not a file or directory", err=True)
            sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo(f"Supported extensions: {', '.join(list_supported_extensions())}")
        sys.exit(1)
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Save both .db and .json
    kg.save(kg_path)
    json_path = kg_path.with_suffix(".json")
    kg.save(json_path)

    entity_count = kg._store.get_entity_count()
    rel_count = kg._store.get_relationship_count()

    click.echo("\nIngestion complete:")
    click.echo(f"  Files processed: {total_files}")
    click.echo(f"  Total chunks: {total_chunks}")
    click.echo(f"  Entities extracted: {entity_count}")
    click.echo(f"  Relationships: {rel_count}")
    click.echo(f"  Knowledge graph: {kg_path}")


@cli.command("list-models")
@click.pass_context
def list_models(ctx):
    """Discover and display available models from all configured providers."""
    from video_processor.providers.discovery import discover_available_models

    models = discover_available_models(force_refresh=True)
    if not models:
        click.echo(
            "No models discovered. Check that at least one API key is set or Ollama is running:"
        )
        click.echo("  OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, or `ollama serve`")
        return

    by_provider: dict[str, list] = {}
    for m in models:
        by_provider.setdefault(m.provider, []).append(m)

    for provider, provider_models in sorted(by_provider.items()):
        click.echo(f"\n{provider.upper()} ({len(provider_models)} models)")
        click.echo("-" * 60)
        for m in provider_models:
            caps = ", ".join(m.capabilities)
            click.echo(f"  {m.id:<40} [{caps}]")

    click.echo(f"\nTotal: {len(models)} models across {len(by_provider)} providers")


@cli.command()
@click.option("--cache-dir", type=click.Path(), help="Path to cache directory")
@click.option("--older-than", type=int, help="Clear entries older than N seconds")
@click.option("--all", "clear_all", is_flag=True, help="Clear all cache entries")
@click.pass_context
def clear_cache(ctx, cache_dir, older_than, clear_all):
    """Clear API response cache."""
    if not cache_dir and not os.environ.get("CACHE_DIR"):
        logging.error("Cache directory not specified")
        sys.exit(1)

    cache_path = Path(cache_dir or os.environ.get("CACHE_DIR"))
    if not cache_path.exists():
        logging.warning(f"Cache directory does not exist: {cache_path}")
        return

    try:
        from video_processor.utils.api_cache import ApiCache

        namespaces = [d.name for d in cache_path.iterdir() if d.is_dir()]
        if not namespaces:
            logging.info("No cache namespaces found")
            return

        total_cleared = 0
        for namespace in namespaces:
            cache = ApiCache(cache_path, namespace)
            cleared = cache.clear(older_than if not clear_all else None)
            total_cleared += cleared
            logging.info(f"Cleared {cleared} entries from {namespace} cache")

        logging.info(f"Total cleared: {total_cleared} entries")
    except Exception as e:
        logging.error(f"Error clearing cache: {e}")
        if ctx.obj["verbose"]:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@cli.command("agent-analyze")
@click.option(
    "--input", "-i", required=True, type=click.Path(exists=True), help="Input video file path"
)
@click.option("--output", "-o", required=True, type=click.Path(), help="Output directory")
@click.option(
    "--depth",
    type=click.Choice(["basic", "standard", "comprehensive"]),
    default="standard",
    help="Initial processing depth (agent may adapt)",
)
@click.option("--title", type=str, help="Title for the analysis report")
@click.option(
    "--provider",
    "-p",
    type=click.Choice(
        [
            "auto",
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
    ),
    default="auto",
    help="API provider",
)
@click.option("--vision-model", type=str, default=None, help="Override model for vision tasks")
@click.option("--chat-model", type=str, default=None, help="Override model for LLM/chat tasks")
@click.pass_context
def agent_analyze(ctx, input, output, depth, title, provider, vision_model, chat_model):
    """Agentic video analysis — adaptive, intelligent processing."""
    from video_processor.agent.orchestrator import AgentOrchestrator
    from video_processor.output_structure import write_video_manifest
    from video_processor.providers.manager import ProviderManager

    prov = None if provider == "auto" else provider
    pm = ProviderManager(vision_model=vision_model, chat_model=chat_model, provider=prov)

    agent = AgentOrchestrator(provider_manager=pm)

    try:
        manifest = agent.process(
            input_path=input,
            output_dir=output,
            initial_depth=depth,
            title=title,
        )
        write_video_manifest(manifest, output)

        if agent.insights:
            logging.info("Agent insights:")
            for insight in agent.insights:
                logging.info(f"  - {insight}")

        logging.info(f"Results at {output}/manifest.json")
    except Exception as e:
        logging.error(f"Error: {e}")
        if ctx.obj["verbose"]:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.argument("request", required=False, default=None)
@click.option("--kb", multiple=True, type=click.Path(exists=True), help="Knowledge base paths")
@click.option("--interactive", "-I", is_flag=True, help="Interactive chat mode")
@click.option("--export", type=click.Path(), default=None, help="Export artifacts to directory")
@click.option(
    "--provider",
    "-p",
    type=click.Choice(
        [
            "auto",
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
    ),
    default="auto",
    help="API provider",
)
@click.option("--chat-model", type=str, default=None, help="Override model for LLM/chat tasks")
@click.pass_context
def agent(ctx, request, kb, interactive, export, provider, chat_model):
    """AI planning agent. Synthesizes knowledge into project plans and artifacts.

    Examples:

        planopticon agent "Create a project plan" --kb ./results

        planopticon agent -I --kb ./videos --kb ./docs

        planopticon agent "Generate a PRD" --export ./output
    """
    # Ensure all skills are registered
    import video_processor.agent.skills  # noqa: F401
    from video_processor.agent.agent_loop import PlanningAgent
    from video_processor.agent.kb_context import KBContext
    from video_processor.agent.skills.base import AgentContext

    # Build provider manager
    pm = None
    try:
        from video_processor.providers.manager import ProviderManager

        prov = None if provider == "auto" else provider
        pm = ProviderManager(chat_model=chat_model, provider=prov)
    except Exception:
        if not interactive:
            click.echo("Warning: could not initialize LLM provider.", err=True)

    # Load knowledge base
    kb_ctx = KBContext()
    if kb:
        for path in kb:
            kb_ctx.add_source(Path(path))
        kb_ctx.load(provider_manager=pm)
        click.echo(kb_ctx.summary())
    else:
        # Auto-discover
        kb_ctx = KBContext.auto_discover(provider_manager=pm)
        if kb_ctx.sources:
            click.echo(kb_ctx.summary())
        else:
            click.echo("No knowledge base found. Use --kb to specify paths.")

    agent_inst = PlanningAgent(
        context=AgentContext(
            knowledge_graph=kb_ctx.knowledge_graph if kb_ctx.sources else None,
            query_engine=kb_ctx.query_engine if kb_ctx.sources else None,
            provider_manager=pm,
        )
    )

    if interactive:
        click.echo("\nPlanOpticon Agent (interactive mode)")
        click.echo("Type your request, or 'quit' to exit.\n")
        while True:
            try:
                line = click.prompt("agent", prompt_suffix="> ")
            except (KeyboardInterrupt, EOFError):
                click.echo("\nBye.")
                break
            if line.strip().lower() in ("quit", "exit", "q"):
                click.echo("Bye.")
                break

            # Check for slash commands
            if line.strip().startswith("/"):
                cmd = line.strip()[1:].split()[0]
                if cmd == "plan":
                    artifacts = agent_inst.execute("Generate a project plan")
                elif cmd == "skills":
                    from video_processor.agent.skills.base import list_skills

                    for s in list_skills():
                        click.echo(f"  {s.name}: {s.description}")
                    continue
                elif cmd == "summary":
                    if kb_ctx.sources:
                        click.echo(kb_ctx.summary())
                    continue
                else:
                    artifacts = agent_inst.execute(line.strip()[1:])

                for a in artifacts:
                    click.echo(f"\n--- {a.name} ({a.artifact_type}) ---\n")
                    click.echo(a.content)
            else:
                response = agent_inst.chat(line)
                click.echo(f"\n{response}\n")
    elif request:
        artifacts = agent_inst.execute(request)
        if not artifacts:
            click.echo("No artifacts generated. Try a more specific request.")
        for artifact in artifacts:
            click.echo(f"\n--- {artifact.name} ({artifact.artifact_type}) ---\n")
            click.echo(artifact.content)

        if export:
            from video_processor.agent.skills.artifact_export import export_artifacts

            export_dir = Path(export)
            export_artifacts(artifacts, export_dir)
            click.echo(f"Exported {len(artifacts)} artifacts to {export_dir}/")
            click.echo(f"Manifest: {export_dir / 'manifest.json'}")
    else:
        click.echo("Provide a request or use -I for interactive mode.")
        click.echo("Example: planopticon agent 'Create a project plan' --kb ./results")


@cli.command()
@click.argument("question", required=False, default=None)
@click.option(
    "--db-path",
    type=click.Path(),
    default=None,
    help="Path to knowledge_graph.db or .json (auto-detected if omitted)",
)
@click.option(
    "--mode",
    type=click.Choice(["direct", "agentic", "auto"]),
    default="auto",
    help="Query mode: direct (no LLM), agentic (LLM), or auto",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "mermaid"]),
    default="text",
    help="Output format",
)
@click.option("--interactive", "-I", is_flag=True, help="Enter interactive REPL mode")
@click.option(
    "--provider",
    "-p",
    type=click.Choice(
        [
            "auto",
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
    ),
    default="auto",
    help="API provider for agentic mode",
)
@click.option("--chat-model", type=str, default=None, help="Override model for agentic mode")
@click.pass_context
def query(ctx, question, db_path, mode, output_format, interactive, provider, chat_model):
    """Query a knowledge graph. Runs stats if no question given.

    Direct commands recognized in QUESTION: stats, entities, relationships,
    neighbors, sources, provenance, sql. Natural language questions use agentic mode.

    Examples:

        planopticon query
        planopticon query stats
        planopticon query "entities --type technology"
        planopticon query "neighbors Alice"
        planopticon query sources
        planopticon query "provenance Alice"
        planopticon query "What was discussed?"
        planopticon query -I
    """
    from video_processor.integrators.graph_discovery import find_nearest_graph
    from video_processor.integrators.graph_query import GraphQueryEngine

    # Resolve graph path
    if db_path:
        graph_path = Path(db_path)
        if not graph_path.exists():
            click.echo(f"Error: file not found: {db_path}", err=True)
            sys.exit(1)
    else:
        graph_path = find_nearest_graph()
        if not graph_path:
            click.echo(
                "No knowledge graph found. Run 'planopticon analyze' first to generate one,\n"
                "or use --db-path to specify a file.",
                err=True,
            )
            sys.exit(1)
        click.echo(f"Using: {graph_path}")

    # Build provider manager for agentic mode
    pm = None
    if mode in ("agentic", "auto"):
        try:
            from video_processor.providers.manager import ProviderManager

            prov = None if provider == "auto" else provider
            pm = ProviderManager(chat_model=chat_model, provider=prov)
        except Exception:
            if mode == "agentic":
                click.echo("Warning: could not initialize LLM provider for agentic mode.", err=True)

    # Create engine
    if graph_path.suffix == ".json":
        engine = GraphQueryEngine.from_json_path(graph_path, provider_manager=pm)
    else:
        engine = GraphQueryEngine.from_db_path(graph_path, provider_manager=pm)

    if interactive:
        _query_repl(engine, output_format)
        return

    if not question:
        question = "stats"

    result = _execute_query(engine, question, mode)
    _print_result(result, output_format)


def _execute_query(engine, question, mode):
    """Parse a question string and execute the appropriate query."""
    parts = question.strip().split()
    cmd = parts[0].lower() if parts else ""

    # Direct commands
    if cmd == "stats":
        return engine.stats()

    if cmd == "entities":
        kwargs = _parse_filter_args(parts[1:])
        return engine.entities(
            name=kwargs.get("name"),
            entity_type=kwargs.get("type"),
            limit=int(kwargs.get("limit", 50)),
        )

    if cmd == "relationships":
        kwargs = _parse_filter_args(parts[1:])
        return engine.relationships(
            source=kwargs.get("source"),
            target=kwargs.get("target"),
            rel_type=kwargs.get("type"),
            limit=int(kwargs.get("limit", 50)),
        )

    if cmd == "neighbors":
        entity_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        return engine.neighbors(entity_name)

    if cmd == "sources":
        return engine.sources()

    if cmd == "provenance":
        entity_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        return engine.provenance(entity_name)

    if cmd == "sql":
        sql_query = " ".join(parts[1:])
        return engine.sql(sql_query)

    # Natural language → agentic (or fallback to entity search in direct mode)
    if mode == "direct":
        return engine.entities(name=question)
    return engine.ask(question)


def _parse_filter_args(parts):
    """Parse --key value pairs from a split argument list."""
    kwargs = {}
    i = 0
    while i < len(parts):
        if parts[i].startswith("--") and i + 1 < len(parts):
            key = parts[i][2:]
            kwargs[key] = parts[i + 1]
            i += 2
        else:
            # Treat as name filter
            kwargs.setdefault("name", parts[i])
            i += 1
    return kwargs


def _print_result(result, output_format):
    """Print a QueryResult in the requested format."""
    if output_format == "json":
        click.echo(result.to_json())
    elif output_format == "mermaid":
        click.echo(result.to_mermaid())
    else:
        click.echo(result.to_text())


def _query_repl(engine, output_format):
    """Interactive REPL for querying the knowledge graph."""
    click.echo("PlanOpticon Knowledge Graph REPL")
    click.echo("Type a query, or 'quit' / 'exit' to leave.\n")
    while True:
        try:
            line = click.prompt("query", prompt_suffix="> ")
        except (KeyboardInterrupt, EOFError):
            click.echo("\nBye.")
            break
        line = line.strip()
        if not line:
            continue
        if line.lower() in ("quit", "exit", "q"):
            click.echo("Bye.")
            break
        result = _execute_query(engine, line, "auto")
        _print_result(result, output_format)
        click.echo()


@cli.command()
@click.argument("service", type=click.Choice(["google", "dropbox"]))
@click.pass_context
def auth(ctx, service):
    """Authenticate with a cloud service (google or dropbox)."""
    if service == "google":
        from video_processor.sources.google_drive import GoogleDriveSource

        source = GoogleDriveSource(use_service_account=False)
        if source.authenticate():
            click.echo("Google Drive authentication successful.")
        else:
            click.echo("Google Drive authentication failed.", err=True)
            sys.exit(1)

    elif service == "dropbox":
        from video_processor.sources.dropbox_source import DropboxSource

        source = DropboxSource()
        if source.authenticate():
            click.echo("Dropbox authentication successful.")
        else:
            click.echo("Dropbox authentication failed.", err=True)
            sys.exit(1)


@cli.group()
def gws():
    """Google Workspace: fetch docs, sheets, and slides via the gws CLI."""
    pass


@gws.command("list")
@click.option("--folder-id", type=str, default=None, help="Drive folder ID to list")
@click.option("--query", "-q", type=str, default=None, help="Drive search query")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def gws_list(folder_id, query, as_json):
    """List documents in Google Drive.

    Examples:

        planopticon gws list

        planopticon gws list --folder-id 1abc...

        planopticon gws list -q "name contains 'PRD'" --json
    """
    from video_processor.sources.gws_source import GWSSource

    source = GWSSource(folder_id=folder_id, query=query)
    if not source.authenticate():
        click.echo("Error: gws CLI not available or not authenticated.", err=True)
        click.echo("Install: npm install -g @googleworkspace/cli", err=True)
        click.echo("Auth:    gws auth login", err=True)
        sys.exit(1)

    files = source.list_videos(folder_id=folder_id)
    if as_json:
        click.echo(json.dumps([f.model_dump() for f in files], indent=2, default=str))
    else:
        if not files:
            click.echo("No documents found.")
            return
        for f in files:
            size = f"{f.size_bytes / 1024:.0f}KB" if f.size_bytes else "—"
            click.echo(f"  {f.id[:12]}…  {size:>8s}  {f.mime_type or ''}  {f.name}")


@gws.command("fetch")
@click.argument("doc_ids", nargs=-1)
@click.option("--folder-id", type=str, default=None, help="Fetch all docs in a folder")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output directory")
def gws_fetch(doc_ids, folder_id, output):
    """Fetch Google Docs/Sheets/Slides as text files.

    Examples:

        planopticon gws fetch DOC_ID1 DOC_ID2 -o ./docs

        planopticon gws fetch --folder-id 1abc... -o ./docs
    """
    from video_processor.sources.gws_source import GWSSource

    source = GWSSource(folder_id=folder_id, doc_ids=list(doc_ids))
    if not source.authenticate():
        click.echo("Error: gws CLI not available or not authenticated.", err=True)
        sys.exit(1)

    out_dir = Path(output) if output else Path.cwd() / "gws_docs"
    out_dir.mkdir(parents=True, exist_ok=True)

    files = source.list_videos(folder_id=folder_id)
    if not files:
        click.echo("No documents found.")
        return

    for f in files:
        safe_name = f.name.replace("/", "_").replace("\\", "_")
        dest = out_dir / f"{safe_name}.txt"
        try:
            source.download(f, dest)
            click.echo(f"  ✓ {f.name} → {dest}")
        except Exception as e:
            click.echo(f"  ✗ {f.name}: {e}", err=True)

    click.echo(f"\nFetched {len(files)} document(s) to {out_dir}")


@gws.command("ingest")
@click.option("--folder-id", type=str, default=None, help="Drive folder ID")
@click.option("--doc-id", type=str, multiple=True, help="Specific doc IDs (repeatable)")
@click.option("--query", "-q", type=str, default=None, help="Drive search query")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output directory")
@click.option("--db-path", type=click.Path(), default=None, help="Existing DB to merge into")
@click.option(
    "-p",
    "--provider",
    type=click.Choice(
        [
            "auto",
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
    ),
    default="auto",
    help="API provider",
)
@click.option("--chat-model", type=str, default=None, help="Override model for LLM/chat tasks")
@click.pass_context
def gws_ingest(ctx, folder_id, doc_id, query, output, db_path, provider, chat_model):
    """Fetch Google Workspace docs and ingest into a knowledge graph.

    Combines gws fetch + planopticon ingest in one step.

    Examples:

        planopticon gws ingest --folder-id 1abc...

        planopticon gws ingest --doc-id DOC1 --doc-id DOC2 -o ./results

        planopticon gws ingest -q "name contains 'spec'" --db-path existing.db
    """
    import tempfile

    from video_processor.integrators.knowledge_graph import KnowledgeGraph
    from video_processor.processors.ingest import ingest_file
    from video_processor.providers.manager import ProviderManager
    from video_processor.sources.gws_source import GWSSource

    source = GWSSource(folder_id=folder_id, doc_ids=list(doc_id), query=query)
    if not source.authenticate():
        click.echo("Error: gws CLI not available or not authenticated.", err=True)
        click.echo("Install: npm install -g @googleworkspace/cli", err=True)
        click.echo("Auth:    gws auth login", err=True)
        sys.exit(1)

    # Fetch docs to temp dir
    files = source.list_videos(folder_id=folder_id)
    if not files:
        click.echo("No documents found.")
        return

    click.echo(f"Found {len(files)} document(s), fetching...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        local_files = []
        for f in files:
            safe_name = f.name.replace("/", "_").replace("\\", "_")
            dest = tmp_path / f"{safe_name}.txt"
            try:
                source.download(f, dest)
                local_files.append(dest)
                click.echo(f"  ✓ {f.name}")
            except Exception as e:
                click.echo(f"  ✗ {f.name}: {e}", err=True)

        if not local_files:
            click.echo("No documents fetched successfully.", err=True)
            sys.exit(1)

        # Set up KG
        prov = None if provider == "auto" else provider
        pm = ProviderManager(chat_model=chat_model, provider=prov)

        if db_path:
            kg_path = Path(db_path)
        elif output:
            out_dir = Path(output)
            out_dir.mkdir(parents=True, exist_ok=True)
            kg_path = out_dir / "knowledge_graph.db"
        else:
            kg_path = Path.cwd() / "knowledge_graph.db"

        kg_path.parent.mkdir(parents=True, exist_ok=True)
        kg = KnowledgeGraph(provider_manager=pm, db_path=kg_path)

        total_chunks = 0
        for lf in local_files:
            try:
                count = ingest_file(lf, kg)
                total_chunks += count
                click.echo(f"  Ingested {lf.stem}: {count} chunks")
            except Exception as e:
                click.echo(f"  Failed to ingest {lf.stem}: {e}", err=True)

        kg.save(kg_path)
        kg.save(kg_path.with_suffix(".json"))

        entity_count = kg._store.get_entity_count()
        rel_count = kg._store.get_relationship_count()

        click.echo("\nIngestion complete:")
        click.echo(f"  Documents: {len(local_files)}")
        click.echo(f"  Chunks: {total_chunks}")
        click.echo(f"  Entities: {entity_count}")
        click.echo(f"  Relationships: {rel_count}")
        click.echo(f"  Knowledge graph: {kg_path}")


@cli.group()
def m365():
    """Microsoft 365: fetch docs from SharePoint and OneDrive via the m365 CLI."""
    pass


@m365.command("list")
@click.option("--web-url", type=str, required=True, help="SharePoint site URL")
@click.option("--folder-url", type=str, required=True, help="Server-relative folder URL")
@click.option("--recursive", is_flag=True, help="Include subfolders")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def m365_list(web_url, folder_url, recursive, as_json):
    """List documents in SharePoint or OneDrive.

    Examples:

        planopticon m365 list --web-url https://contoso.sharepoint.com/sites/proj \\
            --folder-url /sites/proj/Shared\\ Documents

        planopticon m365 list --web-url URL --folder-url FOLDER --recursive --json
    """
    from video_processor.sources.m365_source import M365Source

    source = M365Source(web_url=web_url, folder_url=folder_url, recursive=recursive)
    if not source.authenticate():
        click.echo("Error: m365 CLI not available or not logged in.", err=True)
        click.echo("Install: npm install -g @pnp/cli-microsoft365", err=True)
        click.echo("Auth:    m365 login", err=True)
        sys.exit(1)

    files = source.list_videos()
    if as_json:
        click.echo(json.dumps([f.model_dump() for f in files], indent=2, default=str))
    else:
        if not files:
            click.echo("No documents found.")
            return
        for f in files:
            size = f"{f.size_bytes / 1024:.0f}KB" if f.size_bytes else "—"
            click.echo(f"  {f.id[:12]}…  {size:>8s}  {f.name}")


@m365.command("fetch")
@click.option("--web-url", type=str, required=True, help="SharePoint site URL")
@click.option("--folder-url", type=str, default=None, help="Server-relative folder URL")
@click.option("--file-id", type=str, multiple=True, help="Specific file IDs (repeatable)")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output directory")
def m365_fetch(web_url, folder_url, file_id, output):
    """Fetch SharePoint/OneDrive documents as local files.

    Examples:

        planopticon m365 fetch --web-url URL --folder-url FOLDER -o ./docs

        planopticon m365 fetch --web-url URL --file-id ID1 --file-id ID2 -o ./docs
    """
    from video_processor.sources.m365_source import M365Source

    source = M365Source(web_url=web_url, folder_url=folder_url, file_ids=list(file_id))
    if not source.authenticate():
        click.echo("Error: m365 CLI not available or not logged in.", err=True)
        sys.exit(1)

    out_dir = Path(output) if output else Path.cwd() / "m365_docs"
    out_dir.mkdir(parents=True, exist_ok=True)

    files = source.list_videos()
    if not files:
        click.echo("No documents found.")
        return

    for f in files:
        dest = out_dir / f.name
        try:
            source.download(f, dest)
            click.echo(f"  fetched {f.name}")
        except Exception as e:
            click.echo(f"  failed {f.name}: {e}", err=True)

    click.echo(f"\nFetched {len(files)} document(s) to {out_dir}")


@m365.command("ingest")
@click.option("--web-url", type=str, required=True, help="SharePoint site URL")
@click.option("--folder-url", type=str, default=None, help="Server-relative folder URL")
@click.option("--file-id", type=str, multiple=True, help="Specific file IDs (repeatable)")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output directory")
@click.option("--db-path", type=click.Path(), default=None, help="Existing DB to merge into")
@click.option(
    "-p",
    "--provider",
    type=click.Choice(
        [
            "auto",
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
    ),
    default="auto",
    help="API provider",
)
@click.option("--chat-model", type=str, default=None, help="Override model for LLM/chat tasks")
@click.pass_context
def m365_ingest(ctx, web_url, folder_url, file_id, output, db_path, provider, chat_model):
    """Fetch SharePoint/OneDrive docs and ingest into a knowledge graph.

    Examples:

        planopticon m365 ingest --web-url URL --folder-url FOLDER

        planopticon m365 ingest --web-url URL --file-id ID1 --file-id ID2 -o ./results
    """
    import tempfile

    from video_processor.integrators.knowledge_graph import KnowledgeGraph
    from video_processor.processors.ingest import ingest_file
    from video_processor.providers.manager import ProviderManager
    from video_processor.sources.m365_source import M365Source

    source = M365Source(web_url=web_url, folder_url=folder_url, file_ids=list(file_id))
    if not source.authenticate():
        click.echo("Error: m365 CLI not available or not logged in.", err=True)
        click.echo("Install: npm install -g @pnp/cli-microsoft365", err=True)
        click.echo("Auth:    m365 login", err=True)
        sys.exit(1)

    files = source.list_videos()
    if not files:
        click.echo("No documents found.")
        return

    click.echo(f"Found {len(files)} document(s), fetching...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        local_files = []
        for f in files:
            dest = tmp_path / f.name
            try:
                source.download(f, dest)
                # Extract text for non-text formats
                text_dest = tmp_path / f"{Path(f.name).stem}.txt"
                text = source.download_as_text(f)
                text_dest.write_text(text, encoding="utf-8")
                local_files.append(text_dest)
                click.echo(f"  fetched {f.name}")
            except Exception as e:
                click.echo(f"  failed {f.name}: {e}", err=True)

        if not local_files:
            click.echo("No documents fetched successfully.", err=True)
            sys.exit(1)

        prov = None if provider == "auto" else provider
        pm = ProviderManager(chat_model=chat_model, provider=prov)

        if db_path:
            kg_path = Path(db_path)
        elif output:
            out_dir = Path(output)
            out_dir.mkdir(parents=True, exist_ok=True)
            kg_path = out_dir / "knowledge_graph.db"
        else:
            kg_path = Path.cwd() / "knowledge_graph.db"

        kg_path.parent.mkdir(parents=True, exist_ok=True)
        kg = KnowledgeGraph(provider_manager=pm, db_path=kg_path)

        total_chunks = 0
        for lf in local_files:
            try:
                count = ingest_file(lf, kg)
                total_chunks += count
                click.echo(f"  Ingested {lf.stem}: {count} chunks")
            except Exception as e:
                click.echo(f"  Failed to ingest {lf.stem}: {e}", err=True)

        kg.save(kg_path)
        kg.save(kg_path.with_suffix(".json"))

        entity_count = kg._store.get_entity_count()
        rel_count = kg._store.get_relationship_count()

        click.echo("\nIngestion complete:")
        click.echo(f"  Documents: {len(local_files)}")
        click.echo(f"  Chunks: {total_chunks}")
        click.echo(f"  Entities: {entity_count}")
        click.echo(f"  Relationships: {rel_count}")
        click.echo(f"  Knowledge graph: {kg_path}")


@cli.group()
def export():
    """Export knowledge graphs as markdown docs, notes, or CSV."""
    pass


@export.command("markdown")
@click.argument("db_path", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None, help="Output directory")
@click.option(
    "--type",
    "doc_types",
    type=click.Choice(
        [
            "summary",
            "meeting-notes",
            "glossary",
            "relationship-map",
            "status-report",
            "entity-index",
            "csv",
            "all",
        ]
    ),
    multiple=True,
    default=("all",),
    help="Document types to generate (repeatable)",
)
def export_markdown(db_path, output, doc_types):
    """Generate markdown documents from a knowledge graph.

    No API key needed — pure template-based generation.

    Examples:

        planopticon export markdown knowledge_graph.db

        planopticon export markdown kg.db -o ./docs --type summary --type glossary

        planopticon export markdown kg.db --type meeting-notes --type csv
    """
    from video_processor.exporters.markdown import generate_all
    from video_processor.integrators.knowledge_graph import KnowledgeGraph

    db_path = Path(db_path)
    out_dir = Path(output) if output else Path.cwd() / "export"

    kg = KnowledgeGraph(db_path=db_path)
    kg_data = kg.to_dict()

    types = None if "all" in doc_types else list(doc_types)
    created = generate_all(kg_data, out_dir, doc_types=types)

    click.echo(f"Generated {len(created)} files in {out_dir}/")
    # Show top-level files (not entity briefs)
    for p in sorted(created):
        if p.parent == out_dir:
            click.echo(f"  {p.name}")
    entity_count = len([p for p in created if p.parent != out_dir])
    if entity_count:
        click.echo(f"  entities/ ({entity_count} entity briefs)")


@export.command("obsidian")
@click.argument("db_path", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None, help="Output vault directory")
def export_obsidian(db_path, output):
    """Export knowledge graph as an Obsidian vault with frontmatter and wiki-links.

    Examples:

        planopticon export obsidian knowledge_graph.db -o ./my-vault
    """
    from video_processor.agent.skills.notes_export import export_to_obsidian
    from video_processor.integrators.knowledge_graph import KnowledgeGraph

    db_path = Path(db_path)
    out_dir = Path(output) if output else Path.cwd() / "obsidian-vault"

    kg = KnowledgeGraph(db_path=db_path)
    kg_data = kg.to_dict()
    created = export_to_obsidian(kg_data, out_dir)

    click.echo(f"Exported Obsidian vault: {len(created)} notes in {out_dir}/")


@export.command("notion")
@click.argument("db_path", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None, help="Output directory")
def export_notion(db_path, output):
    """Export knowledge graph as Notion-compatible markdown + CSV database.

    Examples:

        planopticon export notion knowledge_graph.db -o ./notion-export
    """
    from video_processor.agent.skills.notes_export import export_to_notion_md
    from video_processor.integrators.knowledge_graph import KnowledgeGraph

    db_path = Path(db_path)
    out_dir = Path(output) if output else Path.cwd() / "notion-export"

    kg = KnowledgeGraph(db_path=db_path)
    kg_data = kg.to_dict()
    created = export_to_notion_md(kg_data, out_dir)

    click.echo(f"Exported Notion markdown: {len(created)} files in {out_dir}/")


@cli.group()
def wiki():
    """Generate and push GitHub wikis from knowledge graphs."""
    pass


@wiki.command("generate")
@click.argument("db_path", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None, help="Output directory for wiki")
@click.option("--title", type=str, default="Knowledge Base", help="Wiki title")
def wiki_generate(db_path, output, title):
    """Generate a GitHub wiki from a knowledge graph.

    Examples:

        planopticon wiki generate knowledge_graph.db -o ./wiki

        planopticon wiki generate results/kg.db --title "Project Wiki"
    """
    from video_processor.agent.skills.wiki_generator import generate_wiki, write_wiki
    from video_processor.integrators.knowledge_graph import KnowledgeGraph

    db_path = Path(db_path)
    out_dir = Path(output) if output else Path.cwd() / "wiki"

    kg = KnowledgeGraph(db_path=db_path)
    kg_data = kg.to_dict()
    pages = generate_wiki(kg_data, title=title)
    written = write_wiki(pages, out_dir)

    click.echo(f"Generated {len(written)} wiki pages in {out_dir}")
    for p in sorted(written):
        click.echo(f"  {p.name}")


@wiki.command("push")
@click.argument("wiki_dir", type=click.Path(exists=True))
@click.argument("repo", type=str)
@click.option("--message", "-m", type=str, default="Update wiki", help="Commit message")
def wiki_push(wiki_dir, repo, message):
    """Push generated wiki pages to a GitHub wiki repo.

    REPO should be in 'owner/repo' format.

    Examples:

        planopticon wiki push ./wiki ConflictHQ/PlanOpticon

        planopticon wiki push ./wiki owner/repo -m "Add entity pages"
    """
    from video_processor.agent.skills.wiki_generator import push_wiki

    wiki_dir = Path(wiki_dir)
    success = push_wiki(wiki_dir, repo, message=message)
    if success:
        click.echo(f"Wiki pushed to https://github.com/{repo}/wiki")
    else:
        click.echo("Wiki push failed. Check auth and repo permissions.", err=True)
        sys.exit(1)


@cli.group()
def recordings():
    """Fetch meeting recordings from Zoom, Teams, and Google Meet."""
    pass


@recordings.command("zoom-list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def recordings_zoom_list(as_json):
    """List Zoom cloud recordings.

    Requires ZOOM_CLIENT_ID (and optionally ZOOM_CLIENT_SECRET,
    ZOOM_ACCOUNT_ID) environment variables.

    Examples:

        planopticon recordings zoom-list

        planopticon recordings zoom-list --json
    """
    from video_processor.sources.zoom_source import ZoomSource

    source = ZoomSource()
    if not source.authenticate():
        click.echo("Zoom authentication failed.", err=True)
        sys.exit(1)

    files = source.list_videos()
    if as_json:
        click.echo(json.dumps([f.__dict__ for f in files], indent=2, default=str))
    else:
        click.echo(f"Found {len(files)} recording(s):")
        for f in files:
            size = f"{f.size_bytes // 1_000_000} MB" if f.size_bytes else "unknown"
            click.echo(f"  {f.name}  ({size})  {f.modified_at or ''}")


@recordings.command("teams-list")
@click.option("--user-id", default="me", help="Microsoft user ID")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def recordings_teams_list(user_id, as_json):
    """List Teams meeting recordings via the m365 CLI.

    Requires: npm install -g @pnp/cli-microsoft365 && m365 login

    Examples:

        planopticon recordings teams-list

        planopticon recordings teams-list --json
    """
    from video_processor.sources.teams_recording_source import (
        TeamsRecordingSource,
    )

    source = TeamsRecordingSource(user_id=user_id)
    if not source.authenticate():
        click.echo("Teams authentication failed.", err=True)
        sys.exit(1)

    files = source.list_videos()
    if as_json:
        click.echo(json.dumps([f.__dict__ for f in files], indent=2, default=str))
    else:
        click.echo(f"Found {len(files)} recording(s):")
        for f in files:
            click.echo(f"  {f.name}  {f.modified_at or ''}")


@recordings.command("meet-list")
@click.option("--folder-id", default=None, help="Drive folder ID")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def recordings_meet_list(folder_id, as_json):
    """List Google Meet recordings in Drive via the gws CLI.

    Requires: npm install -g @googleworkspace/cli && gws auth login

    Examples:

        planopticon recordings meet-list

        planopticon recordings meet-list --folder-id abc123
    """
    from video_processor.sources.meet_recording_source import (
        MeetRecordingSource,
    )

    source = MeetRecordingSource(drive_folder_id=folder_id)
    if not source.authenticate():
        click.echo("Google Meet authentication failed.", err=True)
        sys.exit(1)

    files = source.list_videos()
    if as_json:
        click.echo(json.dumps([f.__dict__ for f in files], indent=2, default=str))
    else:
        click.echo(f"Found {len(files)} recording(s):")
        for f in files:
            size = f"{f.size_bytes // 1_000_000} MB" if f.size_bytes else "unknown"
            click.echo(f"  {f.name}  ({size})  {f.modified_at or ''}")


@cli.group()
def kg():
    """Knowledge graph utilities: convert, sync, and inspect."""
    pass


@kg.command()
@click.argument("source_path", type=click.Path(exists=True))
@click.argument("dest_path", type=click.Path())
def convert(source_path, dest_path):
    """Convert a knowledge graph between formats.

    Supports .db (SQLite) and .json. The output format is inferred from DEST_PATH extension.

    Examples:

        planopticon kg convert results/knowledge_graph.db output.json
        planopticon kg convert knowledge_graph.json knowledge_graph.db
    """
    from video_processor.integrators.graph_store import InMemoryStore, SQLiteStore

    source_path = Path(source_path)
    dest_path = Path(dest_path)

    if source_path.suffix == dest_path.suffix:
        click.echo(f"Source and destination are the same format ({source_path.suffix}).", err=True)
        sys.exit(1)

    # Load source
    if source_path.suffix == ".db":
        src_store = SQLiteStore(source_path)
    elif source_path.suffix == ".json":
        data = json.loads(source_path.read_text())
        src_store = InMemoryStore()
        for node in data.get("nodes", []):
            descs = node.get("descriptions", [])
            if isinstance(descs, set):
                descs = list(descs)
            src_store.merge_entity(node.get("name", ""), node.get("type", "concept"), descs)
            for occ in node.get("occurrences", []):
                src_store.add_occurrence(
                    node.get("name", ""),
                    occ.get("source", ""),
                    occ.get("timestamp"),
                    occ.get("text"),
                )
        for rel in data.get("relationships", []):
            src_store.add_relationship(
                rel.get("source", ""),
                rel.get("target", ""),
                rel.get("type", "related_to"),
                content_source=rel.get("content_source"),
                timestamp=rel.get("timestamp"),
            )
    else:
        click.echo(f"Unsupported source format: {source_path.suffix}", err=True)
        sys.exit(1)

    # Write destination
    from video_processor.integrators.knowledge_graph import KnowledgeGraph

    kg_obj = KnowledgeGraph(store=src_store)
    kg_obj.save(dest_path)

    e_count = src_store.get_entity_count()
    r_count = src_store.get_relationship_count()
    click.echo(
        f"Converted {source_path} → {dest_path} ({e_count} entities, {r_count} relationships)"
    )

    if hasattr(src_store, "close"):
        src_store.close()


@kg.command()
@click.argument("db_path", type=click.Path(exists=True))
@click.argument("json_path", type=click.Path(), required=False, default=None)
@click.option(
    "--direction",
    type=click.Choice(["db-to-json", "json-to-db", "auto"]),
    default="auto",
    help="Sync direction. 'auto' picks the newer file as source.",
)
def sync(db_path, json_path, direction):
    """Sync a .db and .json knowledge graph, updating the stale one.

    If JSON_PATH is omitted, uses the same name with .json extension.

    Examples:

        planopticon kg sync results/knowledge_graph.db
        planopticon kg sync knowledge_graph.db knowledge_graph.json --direction db-to-json
    """
    db_path = Path(db_path)
    if json_path is None:
        json_path = db_path.with_suffix(".json")
    else:
        json_path = Path(json_path)

    if direction == "auto":
        if not json_path.exists():
            direction = "db-to-json"
        elif not db_path.exists():
            direction = "json-to-db"
        else:
            db_mtime = db_path.stat().st_mtime
            json_mtime = json_path.stat().st_mtime
            direction = "db-to-json" if db_mtime >= json_mtime else "json-to-db"

    from video_processor.integrators.knowledge_graph import KnowledgeGraph

    if direction == "db-to-json":
        kg_obj = KnowledgeGraph(db_path=db_path)
        kg_obj.save(json_path)
        click.echo(f"Synced {db_path} → {json_path}")
    else:
        data = json.loads(json_path.read_text())
        kg_obj = KnowledgeGraph.from_dict(data, db_path=db_path)
        # Force write to db by saving
        kg_obj.save(db_path)
        click.echo(f"Synced {json_path} → {db_path}")

    click.echo(
        f"  {kg_obj._store.get_entity_count()} entities, "
        f"{kg_obj._store.get_relationship_count()} relationships"
    )


@kg.command()
@click.argument("path", type=click.Path(exists=True))
def inspect(path):
    """Show summary stats for a knowledge graph file (.db or .json)."""
    from video_processor.integrators.graph_discovery import describe_graph

    path = Path(path)
    info = describe_graph(path)
    click.echo(f"File: {path}")
    click.echo(f"Store: {info['store_type']}")
    click.echo(f"Entities: {info['entity_count']}")
    click.echo(f"Relationships: {info['relationship_count']}")
    if info["entity_types"]:
        click.echo("Entity types:")
        for t, count in sorted(info["entity_types"].items(), key=lambda x: -x[1]):
            click.echo(f"  {t}: {count}")


@kg.command()
@click.argument("db_path", type=click.Path(exists=True))
@click.option("--provider", "-p", type=str, default="auto")
@click.option("--chat-model", type=str, default=None)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
)
@click.pass_context
def classify(ctx, db_path, provider, chat_model, output_format):
    """Classify knowledge graph entities into planning taxonomy types.

    Examples:\n
        planopticon kg classify results/knowledge_graph.db\n
        planopticon kg classify results/knowledge_graph.db --format json
    """
    from video_processor.integrators.graph_store import create_store
    from video_processor.integrators.taxonomy import TaxonomyClassifier

    db_path = Path(db_path)
    store = create_store(db_path)
    entities = store.get_all_entities()
    relationships = store.get_all_relationships()

    pm = None
    if provider != "none":
        try:
            from video_processor.providers.manager import ProviderManager

            pm = ProviderManager(provider=provider if provider != "auto" else None)
            if chat_model:
                pm.chat_model = chat_model
        except Exception:
            pm = None  # fall back to heuristic-only

    classifier = TaxonomyClassifier(provider_manager=pm)
    planning_entities = classifier.classify_entities(entities, relationships)

    if output_format == "json":
        click.echo(
            json.dumps(
                [pe.model_dump() for pe in planning_entities],
                indent=2,
            )
        )
    else:
        if not planning_entities:
            click.echo("No entities matched planning taxonomy types.")
            return
        workstreams = classifier.organize_by_workstream(planning_entities)
        for group_name, items in sorted(workstreams.items()):
            click.echo(f"\n{group_name.upper()} ({len(items)})")
            for pe in items:
                priority_str = f" [{pe.priority}]" if pe.priority else ""
                click.echo(f"  - {pe.name}{priority_str}")
                if pe.description:
                    click.echo(f"    {pe.description}")

    store.close()


def _interactive_menu(ctx):
    """Show an interactive menu when planopticon is run with no arguments."""
    click.echo()
    click.echo("  PlanOpticon v0.2.0")
    click.echo("  Comprehensive Video Analysis & Knowledge Extraction")
    click.echo()
    click.echo("  1. Analyze a video")
    click.echo("  2. Batch process a folder")
    click.echo("  3. List available models")
    click.echo("  4. Authenticate cloud service")
    click.echo("  5. Clear cache")
    click.echo("  6. Show help")
    click.echo("  7. Query knowledge graph")
    click.echo()

    choice = click.prompt("  Select an option", type=click.IntRange(1, 7))

    if choice == 1:
        input_path = click.prompt("  Video file path", type=click.Path(exists=True))
        output_dir = click.prompt("  Output directory", type=click.Path())
        depth = click.prompt(
            "  Processing depth",
            type=click.Choice(["basic", "standard", "comprehensive"]),
            default="standard",
        )
        provider = click.prompt(
            "  Provider",
            type=click.Choice(
                [
                    "auto",
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
            ),
            default="auto",
        )
        ctx.invoke(
            analyze,
            input=input_path,
            output=output_dir,
            depth=depth,
            focus=None,
            use_gpu=False,
            sampling_rate=0.5,
            change_threshold=0.15,
            periodic_capture=30.0,
            title=None,
            provider=provider,
            vision_model=None,
            chat_model=None,
        )

    elif choice == 2:
        input_dir = click.prompt("  Video directory", type=click.Path(exists=True))
        output_dir = click.prompt("  Output directory", type=click.Path())
        depth = click.prompt(
            "  Processing depth",
            type=click.Choice(["basic", "standard", "comprehensive"]),
            default="standard",
        )
        provider = click.prompt(
            "  Provider",
            type=click.Choice(
                [
                    "auto",
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
            ),
            default="auto",
        )
        ctx.invoke(
            batch,
            input_dir=input_dir,
            output=output_dir,
            depth=depth,
            pattern="*.mp4,*.mkv,*.avi,*.mov,*.webm",
            title="Batch Processing Results",
            provider=provider,
            vision_model=None,
            chat_model=None,
            source="local",
            folder_id=None,
            folder_path=None,
            recursive=True,
        )

    elif choice == 3:
        ctx.invoke(list_models)

    elif choice == 4:
        service = click.prompt(
            "  Cloud service",
            type=click.Choice(["google", "dropbox"]),
        )
        ctx.invoke(auth, service=service)

    elif choice == 5:
        cache_dir = click.prompt("  Cache directory path", type=click.Path())
        clear_all = click.confirm("  Clear all entries?", default=True)
        ctx.invoke(
            clear_cache,
            cache_dir=cache_dir,
            older_than=None,
            clear_all=clear_all,
        )

    elif choice == 6:
        click.echo()
        click.echo(ctx.get_help())

    elif choice == 7:
        ctx.invoke(
            query,
            question=None,
            db_path=None,
            mode="auto",
            output_format="text",
            interactive=True,
            provider="auto",
            chat_model=None,
        )


def main():
    """Entry point for command-line usage."""
    cli(obj={})


if __name__ == "__main__":
    main()
