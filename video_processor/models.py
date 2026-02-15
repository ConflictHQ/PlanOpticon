"""Pydantic data models for PlanOpticon output."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DiagramType(str, Enum):
    """Types of visual content detected in video frames."""
    flowchart = "flowchart"
    sequence = "sequence"
    architecture = "architecture"
    whiteboard = "whiteboard"
    chart = "chart"
    table = "table"
    slide = "slide"
    screenshot = "screenshot"
    unknown = "unknown"


class OutputFormat(str, Enum):
    """Available output formats."""
    markdown = "markdown"
    json = "json"
    html = "html"
    pdf = "pdf"
    svg = "svg"
    png = "png"


class TranscriptSegment(BaseModel):
    """A single segment of transcribed audio."""
    start: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")
    text: str = Field(description="Transcribed text")
    speaker: Optional[str] = Field(default=None, description="Speaker identifier")
    confidence: Optional[float] = Field(default=None, description="Transcription confidence 0-1")


class ActionItem(BaseModel):
    """An action item extracted from content."""
    action: str = Field(description="The action to be taken")
    assignee: Optional[str] = Field(default=None, description="Person responsible")
    deadline: Optional[str] = Field(default=None, description="Deadline or timeframe")
    priority: Optional[str] = Field(default=None, description="Priority level")
    context: Optional[str] = Field(default=None, description="Additional context")
    source: Optional[str] = Field(default=None, description="Where this was found (transcript/diagram)")


class KeyPoint(BaseModel):
    """A key point extracted from content."""
    point: str = Field(description="The key point")
    topic: Optional[str] = Field(default=None, description="Topic or category")
    details: Optional[str] = Field(default=None, description="Supporting details")
    timestamp: Optional[float] = Field(default=None, description="Timestamp in video (seconds)")
    source: Optional[str] = Field(default=None, description="Where this was found")
    related_diagrams: List[int] = Field(default_factory=list, description="Indices of related diagrams")


class DiagramResult(BaseModel):
    """Result from diagram extraction and analysis."""
    frame_index: int = Field(description="Index of the source frame")
    timestamp: Optional[float] = Field(default=None, description="Timestamp in video (seconds)")
    diagram_type: DiagramType = Field(default=DiagramType.unknown, description="Type of diagram")
    confidence: float = Field(default=0.0, description="Detection confidence 0-1")
    description: Optional[str] = Field(default=None, description="Description of the diagram")
    text_content: Optional[str] = Field(default=None, description="Text visible in the diagram")
    elements: List[str] = Field(default_factory=list, description="Identified elements")
    relationships: List[str] = Field(default_factory=list, description="Identified relationships")
    mermaid: Optional[str] = Field(default=None, description="Mermaid syntax representation")
    chart_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Chart data for reproduction (labels, values, chart_type)"
    )
    image_path: Optional[str] = Field(default=None, description="Relative path to original frame")
    svg_path: Optional[str] = Field(default=None, description="Relative path to rendered SVG")
    png_path: Optional[str] = Field(default=None, description="Relative path to rendered PNG")
    mermaid_path: Optional[str] = Field(default=None, description="Relative path to mermaid source")


class ScreenCapture(BaseModel):
    """A screengrab fallback when diagram extraction fails or is uncertain."""
    frame_index: int = Field(description="Index of the source frame")
    timestamp: Optional[float] = Field(default=None, description="Timestamp in video (seconds)")
    caption: Optional[str] = Field(default=None, description="Brief description of the content")
    image_path: Optional[str] = Field(default=None, description="Relative path to screenshot")
    confidence: float = Field(default=0.0, description="Detection confidence that triggered fallback")


class Entity(BaseModel):
    """An entity in the knowledge graph."""
    name: str = Field(description="Entity name")
    type: str = Field(default="concept", description="Entity type (person, concept, time, diagram)")
    descriptions: List[str] = Field(default_factory=list, description="Descriptions of this entity")
    source: Optional[str] = Field(default=None, description="Source attribution (transcript/diagram/both)")
    occurrences: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of occurrences with source, timestamp, text"
    )


class Relationship(BaseModel):
    """A relationship between entities in the knowledge graph."""
    source: str = Field(description="Source entity name")
    target: str = Field(description="Target entity name")
    type: str = Field(default="related_to", description="Relationship type")
    content_source: Optional[str] = Field(default=None, description="Content source identifier")
    timestamp: Optional[float] = Field(default=None, description="Timestamp in seconds")


class KnowledgeGraphData(BaseModel):
    """Serializable knowledge graph data."""
    nodes: List[Entity] = Field(default_factory=list, description="Graph nodes/entities")
    relationships: List[Relationship] = Field(default_factory=list, description="Graph relationships")


class ProcessingStats(BaseModel):
    """Statistics about a processing run."""
    start_time: Optional[str] = Field(default=None, description="ISO format start time")
    end_time: Optional[str] = Field(default=None, description="ISO format end time")
    duration_seconds: Optional[float] = Field(default=None, description="Total processing time")
    frames_extracted: int = Field(default=0)
    people_frames_filtered: int = Field(default=0)
    diagrams_detected: int = Field(default=0)
    screen_captures: int = Field(default=0)
    transcript_duration_seconds: Optional[float] = Field(default=None)
    models_used: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of task to model used (e.g. vision: gpt-4o)"
    )


class VideoMetadata(BaseModel):
    """Metadata about the source video."""
    title: str = Field(description="Video title")
    source_path: Optional[str] = Field(default=None, description="Original video file path")
    duration_seconds: Optional[float] = Field(default=None, description="Video duration")
    resolution: Optional[str] = Field(default=None, description="Video resolution (e.g. 1920x1080)")
    processed_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO format processing timestamp"
    )


class VideoManifest(BaseModel):
    """Manifest for a single video processing run - the single source of truth."""
    version: str = Field(default="1.0", description="Manifest schema version")
    video: VideoMetadata = Field(description="Source video metadata")
    stats: ProcessingStats = Field(default_factory=ProcessingStats)

    # Relative paths to output files
    transcript_json: Optional[str] = Field(default=None)
    transcript_txt: Optional[str] = Field(default=None)
    transcript_srt: Optional[str] = Field(default=None)
    analysis_md: Optional[str] = Field(default=None)
    analysis_html: Optional[str] = Field(default=None)
    analysis_pdf: Optional[str] = Field(default=None)
    knowledge_graph_json: Optional[str] = Field(default=None)
    key_points_json: Optional[str] = Field(default=None)
    action_items_json: Optional[str] = Field(default=None)

    # Inline structured data
    key_points: List[KeyPoint] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    diagrams: List[DiagramResult] = Field(default_factory=list)
    screen_captures: List[ScreenCapture] = Field(default_factory=list)

    # Frame paths
    frame_paths: List[str] = Field(default_factory=list, description="Relative paths to extracted frames")


class BatchVideoEntry(BaseModel):
    """Summary of a single video within a batch."""
    video_name: str
    manifest_path: str = Field(description="Relative path to video manifest")
    status: str = Field(default="pending", description="pending/completed/failed")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    diagrams_count: int = Field(default=0)
    action_items_count: int = Field(default=0)
    key_points_count: int = Field(default=0)
    duration_seconds: Optional[float] = Field(default=None)


class BatchManifest(BaseModel):
    """Manifest for a batch processing run."""
    version: str = Field(default="1.0")
    title: str = Field(default="Batch Processing Results")
    processed_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    stats: ProcessingStats = Field(default_factory=ProcessingStats)

    videos: List[BatchVideoEntry] = Field(default_factory=list)

    # Aggregated counts
    total_videos: int = Field(default=0)
    completed_videos: int = Field(default=0)
    failed_videos: int = Field(default=0)
    total_diagrams: int = Field(default=0)
    total_action_items: int = Field(default=0)
    total_key_points: int = Field(default=0)

    # Batch-level output paths (relative)
    batch_summary_md: Optional[str] = Field(default=None)
    merged_knowledge_graph_json: Optional[str] = Field(default=None)
