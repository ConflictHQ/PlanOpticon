"""Command-line interface for PlanOpticon."""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

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
@click.version_option("0.2.0", prog_name="PlanOpticon")
@click.pass_context
def cli(ctx, verbose):
    """PlanOpticon - Comprehensive Video Analysis & Knowledge Extraction Tool."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)

    if ctx.invoked_subcommand is None:
        _interactive_menu(ctx)


@cli.command()
@click.option("--input", "-i", required=True, type=click.Path(exists=True), help="Input video file path")
@click.option("--output", "-o", required=True, type=click.Path(), help="Output directory")
@click.option(
    "--depth",
    type=click.Choice(["basic", "standard", "comprehensive"]),
    default="standard",
    help="Processing depth",
)
@click.option("--focus", type=str, help='Comma-separated focus areas (e.g., "diagrams,action-items")')
@click.option("--use-gpu", is_flag=True, help="Enable GPU acceleration if available")
@click.option("--sampling-rate", type=float, default=0.5, help="Frame sampling rate")
@click.option("--change-threshold", type=float, default=0.15, help="Visual change threshold")
@click.option("--periodic-capture", type=float, default=30.0, help="Capture a frame every N seconds regardless of change (0 to disable)")
@click.option("--title", type=str, help="Title for the analysis report")
@click.option(
    "--provider",
    "-p",
    type=click.Choice(["auto", "openai", "anthropic", "gemini"]),
    default="auto",
    help="API provider",
)
@click.option("--vision-model", type=str, default=None, help="Override model for vision tasks")
@click.option("--chat-model", type=str, default=None, help="Override model for LLM/chat tasks")
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
):
    """Analyze a single video and extract structured knowledge."""
    from video_processor.pipeline import process_single_video
    from video_processor.providers.manager import ProviderManager

    focus_areas = [a.strip().lower() for a in focus.split(",")] if focus else []
    prov = None if provider == "auto" else provider

    pm = ProviderManager(
        vision_model=vision_model,
        chat_model=chat_model,
        provider=prov,
    )

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
        )
        click.echo(pm.usage.format_summary())
        click.echo(f"\n  Results: {output}/manifest.json")
    except Exception as e:
        logging.error(f"Error: {e}")
        click.echo(pm.usage.format_summary())
        if ctx.obj["verbose"]:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option("--input-dir", "-i", type=click.Path(), default=None, help="Local directory of videos")
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
    type=click.Choice(["auto", "openai", "anthropic", "gemini"]),
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
@click.option("--recursive/--no-recursive", default=True, help="Recurse into subfolders (default: recursive)")
@click.pass_context
def batch(ctx, input_dir, output, depth, pattern, title, provider, vision_model, chat_model, source, folder_id, folder_path, recursive):
    """Process a folder of videos in batch."""
    from video_processor.integrators.knowledge_graph import KnowledgeGraph
    from video_processor.integrators.plan_generator import PlanGenerator
    from video_processor.models import BatchManifest, BatchVideoEntry
    from video_processor.output_structure import (
        create_batch_output_dirs,
        read_video_manifest,
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
            cloud_files = cloud.list_videos(folder_id=folder_id, folder_path=folder_path, patterns=patterns, recursive=recursive)
            local_paths = cloud.download_all(cloud_files, download_dir)
        elif source == "dropbox":
            from video_processor.sources.dropbox_source import DropboxSource

            cloud = DropboxSource()
            if not cloud.authenticate():
                logging.error("Dropbox authentication failed")
                sys.exit(1)
            cloud_files = cloud.list_videos(folder_path=folder_path, patterns=patterns)
            local_paths = cloud.download_all(cloud_files, download_dir)
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
    merged_kg = KnowledgeGraph()

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

            # Merge knowledge graph
            kg_path = video_output / "results" / "knowledge_graph.json"
            if kg_path.exists():
                kg_data = json.loads(kg_path.read_text())
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

    # Save merged knowledge graph
    merged_kg_path = Path(output) / "knowledge_graph.json"
    merged_kg.save(merged_kg_path)

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
    )
    write_batch_manifest(batch_manifest, output)
    click.echo(pm.usage.format_summary())
    click.echo(f"\n  Batch complete: {batch_manifest.completed_videos}/{batch_manifest.total_videos} succeeded")
    click.echo(f"  Results: {output}/batch_manifest.json")


@cli.command("list-models")
@click.pass_context
def list_models(ctx):
    """Discover and display available models from all configured providers."""
    from video_processor.providers.discovery import discover_available_models

    models = discover_available_models(force_refresh=True)
    if not models:
        click.echo("No models discovered. Check that at least one API key is set:")
        click.echo("  OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY")
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
@click.option("--input", "-i", required=True, type=click.Path(exists=True), help="Input video file path")
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
    type=click.Choice(["auto", "openai", "anthropic", "gemini"]),
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
    click.echo()

    choice = click.prompt("  Select an option", type=click.IntRange(1, 6))

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
            type=click.Choice(["auto", "openai", "anthropic", "gemini"]),
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
            type=click.Choice(["auto", "openai", "anthropic", "gemini"]),
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


def main():
    """Entry point for command-line usage."""
    cli(obj={})


if __name__ == "__main__":
    main()
