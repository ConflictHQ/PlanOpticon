# Models API Reference

::: video_processor.models

---

## Overview

The `video_processor.models` module defines all Pydantic data models used throughout PlanOpticon for structured output, serialization, and validation. These models represent everything from individual transcript segments to complete batch processing manifests.

All models inherit from `pydantic.BaseModel` and support JSON serialization via `.model_dump_json()` and deserialization via `.model_validate_json()`.

---

## Enumerations

### DiagramType

Types of visual content detected in video frames.

```python
from video_processor.models import DiagramType
```

| Value | Description |
|---|---|
| `flowchart` | Process flow or decision tree diagrams |
| `sequence` | Sequence or interaction diagrams |
| `architecture` | System architecture diagrams |
| `whiteboard` | Whiteboard drawings or sketches |
| `chart` | Data charts (bar, line, pie, scatter) |
| `table` | Tabular data |
| `slide` | Presentation slides |
| `screenshot` | Application screenshots or screen shares |
| `unknown` | Unclassified visual content |

### OutputFormat

Available output formats for processing results.

| Value | Description |
|---|---|
| `markdown` | Markdown text |
| `json` | JSON data |
| `html` | HTML document |
| `pdf` | PDF document |
| `svg` | SVG vector graphic |
| `png` | PNG raster image |

### PlanningEntityType

Classification types for entities in a planning taxonomy.

| Value | Description |
|---|---|
| `goal` | Project goals or objectives |
| `requirement` | Functional or non-functional requirements |
| `constraint` | Limitations or constraints |
| `decision` | Decisions made during planning |
| `risk` | Identified risks |
| `assumption` | Planning assumptions |
| `dependency` | External or internal dependencies |
| `milestone` | Project milestones |
| `task` | Actionable tasks |
| `feature` | Product features |

### PlanningRelationshipType

Relationship types within a planning taxonomy.

| Value | Description |
|---|---|
| `requires` | Entity A requires entity B |
| `blocked_by` | Entity A is blocked by entity B |
| `has_risk` | Entity A has an associated risk B |
| `depends_on` | Entity A depends on entity B |
| `addresses` | Entity A addresses entity B |
| `has_tradeoff` | Entity A involves a tradeoff with entity B |
| `delivers` | Entity A delivers entity B |
| `implements` | Entity A implements entity B |
| `parent_of` | Entity A is the parent of entity B |

---

## Protocols

### ProgressCallback

A runtime-checkable protocol for receiving pipeline progress updates. Implement this interface to integrate custom progress reporting (e.g., web UI, logging).

```python
from video_processor.models import ProgressCallback

class MyProgress:
    def on_step_start(self, step: str, index: int, total: int) -> None:
        print(f"Starting {step} ({index}/{total})")

    def on_step_complete(self, step: str, index: int, total: int) -> None:
        print(f"Completed {step} ({index}/{total})")

    def on_progress(self, step: str, percent: float, message: str = "") -> None:
        print(f"{step}: {percent:.0f}% {message}")

assert isinstance(MyProgress(), ProgressCallback)  # True
```

**Methods:**

| Method | Parameters | Description |
|---|---|---|
| `on_step_start` | `step: str`, `index: int`, `total: int` | Called when a pipeline step begins |
| `on_step_complete` | `step: str`, `index: int`, `total: int` | Called when a pipeline step finishes |
| `on_progress` | `step: str`, `percent: float`, `message: str` | Called with incremental progress updates |

---

## Transcript Models

### TranscriptSegment

A single segment of transcribed audio with timing and optional speaker identification.

| Field | Type | Default | Description |
|---|---|---|---|
| `start` | `float` | *required* | Start time in seconds |
| `end` | `float` | *required* | End time in seconds |
| `text` | `str` | *required* | Transcribed text content |
| `speaker` | `Optional[str]` | `None` | Speaker identifier (e.g., "Speaker 1") |
| `confidence` | `Optional[float]` | `None` | Transcription confidence score (0.0 to 1.0) |

```json
{
  "start": 12.5,
  "end": 15.3,
  "text": "We should migrate to the new API by next quarter.",
  "speaker": "Alice",
  "confidence": 0.95
}
```

---

## Content Extraction Models

### ActionItem

An action item extracted from transcript or diagram content.

| Field | Type | Default | Description |
|---|---|---|---|
| `action` | `str` | *required* | The action to be taken |
| `assignee` | `Optional[str]` | `None` | Person responsible for the action |
| `deadline` | `Optional[str]` | `None` | Deadline or timeframe |
| `priority` | `Optional[str]` | `None` | Priority level (e.g., "high", "medium", "low") |
| `context` | `Optional[str]` | `None` | Additional context or notes |
| `source` | `Optional[str]` | `None` | Where this was found: `"transcript"`, `"diagram"`, or `"both"` |

```json
{
  "action": "Migrate authentication service to OAuth 2.0",
  "assignee": "Bob",
  "deadline": "Q2 2026",
  "priority": "high",
  "context": "at 245s",
  "source": "transcript"
}
```

### KeyPoint

A key point extracted from content, optionally linked to diagrams.

| Field | Type | Default | Description |
|---|---|---|---|
| `point` | `str` | *required* | The key point text |
| `topic` | `Optional[str]` | `None` | Topic or category |
| `details` | `Optional[str]` | `None` | Supporting details |
| `timestamp` | `Optional[float]` | `None` | Timestamp in video (seconds) |
| `source` | `Optional[str]` | `None` | Where this was found |
| `related_diagrams` | `List[int]` | `[]` | Indices of related diagrams in the manifest |

```json
{
  "point": "Team decided to use FalkorDB for graph storage",
  "topic": "Architecture",
  "details": "Embedded database avoids infrastructure overhead for CLI use",
  "timestamp": 342.0,
  "source": "transcript",
  "related_diagrams": [0, 2]
}
```

---

## Diagram Models

### DiagramResult

Result from diagram extraction and analysis. Contains structured data extracted from visual content, along with paths to output files.

| Field | Type | Default | Description |
|---|---|---|---|
| `frame_index` | `int` | *required* | Index of the source frame |
| `timestamp` | `Optional[float]` | `None` | Timestamp in video (seconds) |
| `diagram_type` | `DiagramType` | `unknown` | Type of diagram detected |
| `confidence` | `float` | `0.0` | Detection confidence (0.0 to 1.0) |
| `description` | `Optional[str]` | `None` | Detailed description of the diagram |
| `text_content` | `Optional[str]` | `None` | All visible text, preserving structure |
| `elements` | `List[str]` | `[]` | Identified elements or components |
| `relationships` | `List[str]` | `[]` | Identified relationships (e.g., `"A -> B: connects"`) |
| `mermaid` | `Optional[str]` | `None` | Mermaid syntax representation |
| `chart_data` | `Optional[Dict[str, Any]]` | `None` | Extractable chart data (`labels`, `values`, `chart_type`) |
| `image_path` | `Optional[str]` | `None` | Relative path to original frame image |
| `svg_path` | `Optional[str]` | `None` | Relative path to rendered SVG |
| `png_path` | `Optional[str]` | `None` | Relative path to rendered PNG |
| `mermaid_path` | `Optional[str]` | `None` | Relative path to mermaid source file |

```json
{
  "frame_index": 5,
  "timestamp": 120.0,
  "diagram_type": "architecture",
  "confidence": 0.92,
  "description": "Microservices architecture showing API gateway, auth service, and database layer",
  "text_content": "API Gateway\nAuth Service\nUser DB\nPostgreSQL",
  "elements": ["API Gateway", "Auth Service", "User DB", "PostgreSQL"],
  "relationships": ["API Gateway -> Auth Service: authenticates", "Auth Service -> User DB: queries"],
  "mermaid": "graph LR\n  A[API Gateway] --> B[Auth Service]\n  B --> C[User DB]",
  "chart_data": null,
  "image_path": "diagrams/diagram_0.jpg",
  "svg_path": null,
  "png_path": null,
  "mermaid_path": "diagrams/diagram_0.mermaid"
}
```

### ScreenCapture

A screengrab fallback created when diagram extraction fails or confidence is too low for full analysis.

| Field | Type | Default | Description |
|---|---|---|---|
| `frame_index` | `int` | *required* | Index of the source frame |
| `timestamp` | `Optional[float]` | `None` | Timestamp in video (seconds) |
| `caption` | `Optional[str]` | `None` | Brief description of the content |
| `image_path` | `Optional[str]` | `None` | Relative path to screenshot image |
| `confidence` | `float` | `0.0` | Detection confidence that triggered fallback |

```json
{
  "frame_index": 8,
  "timestamp": 195.0,
  "caption": "Code editor showing a Python function definition",
  "image_path": "captures/capture_0.jpg",
  "confidence": 0.45
}
```

---

## Knowledge Graph Models

### Entity

An entity in the knowledge graph, representing a person, concept, technology, or other named item extracted from content.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | *required* | Entity name |
| `type` | `str` | `"concept"` | Entity type: `"person"`, `"concept"`, `"technology"`, `"time"`, `"diagram"` |
| `descriptions` | `List[str]` | `[]` | Accumulated descriptions of this entity |
| `source` | `Optional[str]` | `None` | Source attribution: `"transcript"`, `"diagram"`, or `"both"` |
| `occurrences` | `List[Dict[str, Any]]` | `[]` | Occurrences with source, timestamp, and text context |

```json
{
  "name": "FalkorDB",
  "type": "technology",
  "descriptions": ["Embedded graph database", "Supports Cypher queries"],
  "source": "both",
  "occurrences": [
    {"source": "transcript", "timestamp": 120.0, "text": "We chose FalkorDB for graph storage"},
    {"source": "diagram", "text": "FalkorDB Lite"}
  ]
}
```

### Relationship

A directed relationship between two entities in the knowledge graph.

| Field | Type | Default | Description |
|---|---|---|---|
| `source` | `str` | *required* | Source entity name |
| `target` | `str` | *required* | Target entity name |
| `type` | `str` | `"related_to"` | Relationship type (e.g., `"uses"`, `"manages"`, `"related_to"`) |
| `content_source` | `Optional[str]` | `None` | Content source identifier |
| `timestamp` | `Optional[float]` | `None` | Timestamp in seconds |

```json
{
  "source": "PlanOpticon",
  "target": "FalkorDB",
  "type": "uses",
  "content_source": "transcript",
  "timestamp": 125.0
}
```

### SourceRecord

A content source registered in the knowledge graph for provenance tracking.

| Field | Type | Default | Description |
|---|---|---|---|
| `source_id` | `str` | *required* | Unique identifier for this source |
| `source_type` | `str` | *required* | Source type: `"video"`, `"document"`, `"url"`, `"api"`, `"manual"` |
| `title` | `str` | *required* | Human-readable title |
| `path` | `Optional[str]` | `None` | Local file path |
| `url` | `Optional[str]` | `None` | URL if applicable |
| `mime_type` | `Optional[str]` | `None` | MIME type of the source |
| `ingested_at` | `str` | *auto* | ISO format ingestion timestamp (auto-generated) |
| `metadata` | `Dict[str, Any]` | `{}` | Additional source metadata |

```json
{
  "source_id": "vid_abc123",
  "source_type": "video",
  "title": "Sprint Planning Meeting - Jan 15",
  "path": "/recordings/sprint-planning.mp4",
  "url": null,
  "mime_type": "video/mp4",
  "ingested_at": "2026-01-15T10:30:00",
  "metadata": {"duration": 3600, "resolution": "1920x1080"}
}
```

### KnowledgeGraphData

Serializable knowledge graph data containing all nodes, relationships, and source provenance.

| Field | Type | Default | Description |
|---|---|---|---|
| `nodes` | `List[Entity]` | `[]` | Graph nodes/entities |
| `relationships` | `List[Relationship]` | `[]` | Graph relationships |
| `sources` | `List[SourceRecord]` | `[]` | Content sources for provenance tracking |

---

## Planning Models

### PlanningEntity

An entity classified for planning purposes, with priority and status tracking.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | *required* | Entity name |
| `planning_type` | `PlanningEntityType` | *required* | Planning classification |
| `description` | `str` | `""` | Detailed description |
| `priority` | `Optional[str]` | `None` | Priority: `"high"`, `"medium"`, `"low"` |
| `status` | `Optional[str]` | `None` | Status: `"identified"`, `"confirmed"`, `"resolved"` |
| `source_entities` | `List[str]` | `[]` | Names of source KG entities this was derived from |
| `metadata` | `Dict[str, Any]` | `{}` | Additional metadata |

```json
{
  "name": "Migrate to OAuth 2.0",
  "planning_type": "task",
  "description": "Replace custom auth with OAuth 2.0 across all services",
  "priority": "high",
  "status": "identified",
  "source_entities": ["OAuth", "Authentication Service"],
  "metadata": {}
}
```

---

## Processing and Metadata Models

### ProcessingStats

Statistics about a processing run, including model usage tracking.

| Field | Type | Default | Description |
|---|---|---|---|
| `start_time` | `Optional[str]` | `None` | ISO format start time |
| `end_time` | `Optional[str]` | `None` | ISO format end time |
| `duration_seconds` | `Optional[float]` | `None` | Total processing time |
| `frames_extracted` | `int` | `0` | Number of frames extracted from video |
| `people_frames_filtered` | `int` | `0` | Frames filtered out (contained people/webcam) |
| `diagrams_detected` | `int` | `0` | Number of diagrams detected |
| `screen_captures` | `int` | `0` | Number of screen captures saved |
| `transcript_duration_seconds` | `Optional[float]` | `None` | Duration of transcribed audio |
| `models_used` | `Dict[str, str]` | `{}` | Map of task to model used (e.g., `{"vision": "gpt-4o"}`) |

### VideoMetadata

Metadata about the source video file.

| Field | Type | Default | Description |
|---|---|---|---|
| `title` | `str` | *required* | Video title |
| `source_path` | `Optional[str]` | `None` | Original video file path |
| `duration_seconds` | `Optional[float]` | `None` | Video duration in seconds |
| `resolution` | `Optional[str]` | `None` | Video resolution (e.g., `"1920x1080"`) |
| `processed_at` | `str` | *auto* | ISO format processing timestamp |

---

## Manifest Models

### VideoManifest

The single source of truth for a video processing run. Contains all output paths, inline structured data, and processing statistics.

| Field | Type | Default | Description |
|---|---|---|---|
| `version` | `str` | `"1.0"` | Manifest schema version |
| `video` | `VideoMetadata` | *required* | Source video metadata |
| `stats` | `ProcessingStats` | *default* | Processing statistics |
| `transcript_json` | `Optional[str]` | `None` | Relative path to transcript JSON |
| `transcript_txt` | `Optional[str]` | `None` | Relative path to transcript text |
| `transcript_srt` | `Optional[str]` | `None` | Relative path to SRT subtitles |
| `analysis_md` | `Optional[str]` | `None` | Relative path to analysis Markdown |
| `analysis_html` | `Optional[str]` | `None` | Relative path to analysis HTML |
| `analysis_pdf` | `Optional[str]` | `None` | Relative path to analysis PDF |
| `knowledge_graph_json` | `Optional[str]` | `None` | Relative path to knowledge graph JSON |
| `knowledge_graph_db` | `Optional[str]` | `None` | Relative path to knowledge graph DB |
| `key_points_json` | `Optional[str]` | `None` | Relative path to key points JSON |
| `action_items_json` | `Optional[str]` | `None` | Relative path to action items JSON |
| `key_points` | `List[KeyPoint]` | `[]` | Inline key points data |
| `action_items` | `List[ActionItem]` | `[]` | Inline action items data |
| `diagrams` | `List[DiagramResult]` | `[]` | Inline diagram results |
| `screen_captures` | `List[ScreenCapture]` | `[]` | Inline screen captures |
| `frame_paths` | `List[str]` | `[]` | Relative paths to extracted frames |

```python
from video_processor.models import VideoManifest, VideoMetadata

manifest = VideoManifest(
    video=VideoMetadata(title="Sprint Planning"),
    key_points=[...],
    action_items=[...],
    diagrams=[...],
)

# Serialize to JSON
manifest.model_dump_json(indent=2)

# Load from file
loaded = VideoManifest.model_validate_json(Path("manifest.json").read_text())
```

### BatchVideoEntry

Summary of a single video within a batch processing run.

| Field | Type | Default | Description |
|---|---|---|---|
| `video_name` | `str` | *required* | Video file name |
| `manifest_path` | `str` | *required* | Relative path to the video's manifest file |
| `status` | `str` | `"pending"` | Processing status: `"pending"`, `"completed"`, `"failed"` |
| `error` | `Optional[str]` | `None` | Error message if processing failed |
| `diagrams_count` | `int` | `0` | Number of diagrams detected |
| `action_items_count` | `int` | `0` | Number of action items extracted |
| `key_points_count` | `int` | `0` | Number of key points extracted |
| `duration_seconds` | `Optional[float]` | `None` | Processing duration |

### BatchManifest

Manifest for a batch processing run across multiple videos.

| Field | Type | Default | Description |
|---|---|---|---|
| `version` | `str` | `"1.0"` | Manifest schema version |
| `title` | `str` | `"Batch Processing Results"` | Batch title |
| `processed_at` | `str` | *auto* | ISO format timestamp |
| `stats` | `ProcessingStats` | *default* | Aggregated processing statistics |
| `videos` | `List[BatchVideoEntry]` | `[]` | Per-video summaries |
| `total_videos` | `int` | `0` | Total number of videos in batch |
| `completed_videos` | `int` | `0` | Successfully processed videos |
| `failed_videos` | `int` | `0` | Videos that failed processing |
| `total_diagrams` | `int` | `0` | Total diagrams across all videos |
| `total_action_items` | `int` | `0` | Total action items across all videos |
| `total_key_points` | `int` | `0` | Total key points across all videos |
| `batch_summary_md` | `Optional[str]` | `None` | Relative path to batch summary Markdown |
| `merged_knowledge_graph_json` | `Optional[str]` | `None` | Relative path to merged KG JSON |
| `merged_knowledge_graph_db` | `Optional[str]` | `None` | Relative path to merged KG database |

```python
from video_processor.models import BatchManifest

batch = BatchManifest(
    title="Weekly Recordings",
    total_videos=5,
    completed_videos=4,
    failed_videos=1,
)
```
