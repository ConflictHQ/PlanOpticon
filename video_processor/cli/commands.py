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

from video_processor.extractors.frame_extractor import extract_frames, save_frames
from video_processor.extractors.audio_extractor import AudioExtractor
from video_processor.api.transcription_api import TranscriptionAPI
from video_processor.api.vision_api import VisionAPI
from video_processor.analyzers.diagram_analyzer import DiagramAnalyzer
from video_processor.integrators.knowledge_graph import KnowledgeGraph
from video_processor.integrators.plan_generator import PlanGenerator
from video_processor.cli.output_formatter import OutputFormatter

# Configure logging
def setup_logging(verbose: bool = False) -> None:
    """Set up logging with color formatting."""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create a formatter that includes timestamp, level, and message
    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    
    # Set up console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers and add our handler
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)
    root_logger.addHandler(console_handler)

# Main CLI group
@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.version_option('0.1.0', prog_name='PlanOpticon')
@click.pass_context
def cli(ctx, verbose):
    """PlanOpticon - Comprehensive Video Analysis & Knowledge Extraction Tool."""
    # Initialize context
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    
    # Set up logging
    setup_logging(verbose)

@cli.command()
@click.option('--input', '-i', required=True, type=click.Path(exists=True),
              help='Input video file path')
@click.option('--output', '-o', required=True, type=click.Path(),
              help='Output directory for extracted content')
@click.option('--depth', type=click.Choice(['basic', 'standard', 'comprehensive']),
              default='standard', help='Processing depth')
@click.option('--focus', type=str, help='Comma-separated list of focus areas (e.g., "diagrams,action-items")')
@click.option('--use-gpu', is_flag=True, help='Enable GPU acceleration if available')
@click.option('--sampling-rate', type=float, default=0.5,
              help='Frame sampling rate (1.0 = every frame)')
@click.option('--change-threshold', type=float, default=0.15,
              help='Threshold for detecting visual changes between frames')
@click.option('--title', type=str, help='Title for the analysis report')
@click.option('--provider', '-p', type=click.Choice(['auto', 'openai', 'anthropic', 'gemini']),
              default='auto', help='API provider (auto selects best available)')
@click.option('--vision-model', type=str, default=None, help='Override model for vision tasks')
@click.option('--chat-model', type=str, default=None, help='Override model for LLM/chat tasks')
@click.pass_context
def analyze(ctx, input, output, depth, focus, use_gpu, sampling_rate, change_threshold, title,
            provider, vision_model, chat_model):
    """Analyze video content and extract structured knowledge."""
    start_time = time.time()
    
    # Convert paths
    input_path = Path(input)
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Set up cache directory
    cache_dir = output_dir / "cache"
    cache_dir.mkdir(exist_ok=True)
    
    # Handle focus areas
    focus_areas = []
    if focus:
        focus_areas = [area.strip().lower() for area in focus.split(',')]
    
    # Set video title if not provided
    if not title:
        title = f"Analysis of {input_path.stem}"
    
    # Log analysis parameters
    logging.info(f"Starting analysis of {input_path}")
    logging.info(f"Processing depth: {depth}")
    if focus_areas:
        logging.info(f"Focus areas: {', '.join(focus_areas)}")
    
    try:
        # Create subdirectories
        frames_dir = output_dir / "frames"
        audio_dir = output_dir / "audio"
        transcript_dir = output_dir / "transcript"
        diagrams_dir = output_dir / "diagrams"
        results_dir = output_dir / "results"
        
        for directory in [frames_dir, audio_dir, transcript_dir, diagrams_dir, results_dir]:
            directory.mkdir(exist_ok=True)
        
        # Step 1: Extract frames
        logging.info("Extracting video frames...")
        frames = extract_frames(
            input_path,
            sampling_rate=sampling_rate,
            change_threshold=change_threshold,
            disable_gpu=not use_gpu
        )
        logging.info(f"Extracted {len(frames)} frames")
        
        # Save frames
        frame_paths = save_frames(frames, frames_dir, "frame")
        logging.info(f"Saved frames to {frames_dir}")
        
        # Step 2: Extract audio
        logging.info("Extracting audio...")
        audio_extractor = AudioExtractor()
        audio_path = audio_extractor.extract_audio(
            input_path,
            output_path=audio_dir / f"{input_path.stem}.wav"
        )
        audio_props = audio_extractor.get_audio_properties(audio_path)
        logging.info(f"Extracted audio: {audio_props['duration']:.2f}s, {audio_props['sample_rate']} Hz")
        
        # Step 3: Transcribe audio
        logging.info("Transcribing audio...")
        transcription_api = TranscriptionAPI(
            provider="openai",  # Could be configurable
            cache_dir=cache_dir,
            use_cache=True
        )
        
        # Process based on depth
        detect_speakers = depth != "basic"
        transcription = transcription_api.transcribe_audio(
            audio_path,
            detect_speakers=detect_speakers,
            speakers=2 if detect_speakers else 1  # Default to 2 speakers if detecting
        )
        
        # Save transcript in different formats
        transcript_path = transcription_api.save_transcript(
            transcription,
            transcript_dir / f"{input_path.stem}",
            format="json"
        )
        transcription_api.save_transcript(
            transcription,
            transcript_dir / f"{input_path.stem}",
            format="txt"
        )
        transcription_api.save_transcript(
            transcription,
            transcript_dir / f"{input_path.stem}",
            format="srt"
        )
        
        logging.info(f"Saved transcripts to {transcript_dir}")
        
        # Step 4: Diagram extraction and analysis
        logging.info("Analyzing visual elements...")
        
        # Initialize vision API
        vision_api = VisionAPI(
            provider="openai",  # Could be configurable
            cache_dir=cache_dir,
            use_cache=True
        )
        
        # Initialize diagram analyzer
        diagram_analyzer = DiagramAnalyzer(
            vision_api=vision_api,
            cache_dir=cache_dir,
            use_cache=True
        )
        
        # Detect and analyze diagrams
        # We pass frame paths instead of numpy arrays for better caching
        logging.info("Detecting diagrams in frames...")
        diagrams = []
        
        # Skip diagram detection for basic depth
        if depth != "basic" and (not focus_areas or "diagrams" in focus_areas):
            # For demo purposes, limit to a subset of frames to reduce API costs
            max_frames_to_analyze = 10 if depth == "standard" else 20
            frame_subset = frame_paths[:min(max_frames_to_analyze, len(frame_paths))]
            
            detected_frames = diagram_analyzer.detect_diagrams(frame_subset)
            
            if detected_frames:
                logging.info(f"Detected {len(detected_frames)} potential diagrams")
                
                # Process each detected diagram
                for idx, confidence in detected_frames:
                    if idx < len(frame_subset):
                        frame_path = frame_subset[idx]
                        logging.info(f"Analyzing diagram in frame {idx} (confidence: {confidence:.2f})")
                        
                        # Analyze the diagram
                        analysis = diagram_analyzer.analyze_diagram(frame_path, extract_text=True)
                        
                        # Add frame metadata
                        analysis['frame_index'] = idx
                        analysis['confidence'] = confidence
                        analysis['image_path'] = frame_path
                        
                        # Generate Mermaid if sufficient analysis available
                        if depth == "comprehensive" and 'semantic_analysis' in analysis and analysis.get('text_content'):
                            analysis['mermaid'] = diagram_analyzer.generate_mermaid(analysis)
                        
                        # Save diagram image to diagrams directory
                        import shutil
                        diagram_path = diagrams_dir / f"diagram_{idx}.jpg"
                        shutil.copy2(frame_path, diagram_path)
                        analysis['image_path'] = str(diagram_path)
                        
                        # Save analysis as JSON
                        diagram_json_path = diagrams_dir / f"diagram_{idx}.json"
                        with open(diagram_json_path, 'w') as f:
                            json.dump(analysis, f, indent=2)
                        
                        diagrams.append(analysis)
            else:
                logging.info("No diagrams detected in analyzed frames")
        
        # Step 5: Generate knowledge graph and markdown report
        logging.info("Generating knowledge graph and report...")
        
        # Initialize knowledge graph
        knowledge_graph = KnowledgeGraph(
            cache_dir=cache_dir,
            use_cache=True
        )
        
        # Initialize plan generator
        plan_generator = PlanGenerator(
            knowledge_graph=knowledge_graph,
            cache_dir=cache_dir,
            use_cache=True
        )
        
        # Process transcript and diagrams
        with open(transcript_path) as f:
            transcript_data = json.load(f)
        
        # Process into knowledge graph
        knowledge_graph.process_transcript(transcript_data)
        if diagrams:
            knowledge_graph.process_diagrams(diagrams)
        
        # Save knowledge graph
        kg_path = knowledge_graph.save(results_dir / "knowledge_graph.json")
        
        # Extract key points
        key_points = plan_generator.extract_key_points(transcript_data)
        
        # Generate markdown
        with open(kg_path) as f:
            kg_data = json.load(f)
        
        markdown_path = results_dir / "analysis.md"
        markdown_content = plan_generator.generate_markdown(
            transcript=transcript_data,
            key_points=key_points,
            diagrams=diagrams,
            knowledge_graph=kg_data,
            video_title=title,
            output_path=markdown_path
        )
        
        # Format and organize outputs
        output_formatter = OutputFormatter(output_dir)
        outputs = output_formatter.organize_outputs(
            markdown_path=markdown_path,
            knowledge_graph_path=kg_path,
            diagrams=diagrams,
            frames_dir=frames_dir,
            transcript_path=transcript_path
        )
        
        # Create HTML index
        index_path = output_formatter.create_html_index(outputs)
        
        # Finalize
        elapsed = time.time() - start_time
        logging.info(f"Analysis completed in {elapsed:.2f} seconds")
        logging.info(f"Results available at {index_path}")
        
    except Exception as e:
        logging.error(f"Error during analysis: {str(e)}")
        if ctx.obj['verbose']:
            import traceback
            traceback.print_exc()
        sys.exit(1)

@cli.command()
@click.option('--cache-dir', type=click.Path(), help='Path to cache directory')
@click.option('--older-than', type=int, help='Clear entries older than N seconds')
@click.option('--all', 'clear_all', is_flag=True, help='Clear all cache entries')
@click.pass_context
def clear_cache(ctx, cache_dir, older_than, clear_all):
    """Clear API response cache."""
    if not cache_dir and not os.environ.get('CACHE_DIR'):
        logging.error("Cache directory not specified")
        sys.exit(1)
    
    cache_path = Path(cache_dir or os.environ.get('CACHE_DIR'))
    
    if not cache_path.exists():
        logging.warning(f"Cache directory does not exist: {cache_path}")
        return
    
    try:
        # Clear specific caches
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
        logging.error(f"Error clearing cache: {str(e)}")
        if ctx.obj['verbose']:
            import traceback
            traceback.print_exc()
        sys.exit(1)

@cli.command('list-models')
@click.pass_context
def list_models(ctx):
    """Discover and display available models from all configured providers."""
    from video_processor.providers.discovery import discover_available_models

    models = discover_available_models(force_refresh=True)
    if not models:
        click.echo("No models discovered. Check that at least one API key is set:")
        click.echo("  OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY")
        return

    # Group by provider
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


def main():
    """Entry point for command-line usage."""
    cli(obj={})

if __name__ == '__main__':
    main()
