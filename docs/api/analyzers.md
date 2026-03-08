# Analyzers API Reference

::: video_processor.analyzers.diagram_analyzer

::: video_processor.analyzers.content_analyzer

::: video_processor.analyzers.action_detector

---

## Overview

The analyzers module contains the core content extraction logic for PlanOpticon. These analyzers process video frames and transcripts to extract structured knowledge: diagrams, key points, action items, and cross-referenced entities.

All analyzers accept an optional `ProviderManager` instance. When provided, they use LLM capabilities for richer extraction. Without one, they fall back to heuristic/pattern-based methods where possible.

---

## DiagramAnalyzer

```python
from video_processor.analyzers.diagram_analyzer import DiagramAnalyzer
```

Vision model-based diagram detection and analysis. Classifies video frames as diagrams, slides, screenshots, or other content, then performs full extraction on high-confidence frames.

### Constructor

```python
def __init__(
    self,
    provider_manager: Optional[ProviderManager] = None,
    confidence_threshold: float = 0.3,
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `provider_manager` | `Optional[ProviderManager]` | `None` | LLM provider (creates a default if not provided) |
| `confidence_threshold` | `float` | `0.3` | Minimum confidence to process a frame at all |

### classify_frame()

```python
def classify_frame(self, image_path: Union[str, Path]) -> dict
```

Classify a single frame using a vision model. Determines whether the frame contains a diagram, slide, or other visual content worth extracting.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `image_path` | `Union[str, Path]` | Path to the frame image file |

**Returns:** `dict` with the following keys:

| Key | Type | Description |
|---|---|---|
| `is_diagram` | `bool` | Whether the frame contains extractable content |
| `diagram_type` | `str` | One of: `flowchart`, `sequence`, `architecture`, `whiteboard`, `chart`, `table`, `slide`, `screenshot`, `unknown` |
| `confidence` | `float` | Detection confidence from 0.0 to 1.0 |
| `content_type` | `str` | Content category: `slide`, `diagram`, `document`, `screen_share`, `whiteboard`, `chart`, `person`, `other` |
| `brief_description` | `str` | One-sentence description of the frame content |

**Important:** Frames showing people, webcam feeds, or video conference participant views return `confidence: 0.0`. The classifier is tuned to detect only shared/presented content.

```python
analyzer = DiagramAnalyzer()
result = analyzer.classify_frame("/path/to/frame_042.jpg")
if result["confidence"] >= 0.7:
    print(f"Diagram detected: {result['diagram_type']}")
```

### analyze_diagram_single_pass()

```python
def analyze_diagram_single_pass(self, image_path: Union[str, Path]) -> dict
```

Full single-pass diagram analysis. Extracts description, text content, elements, relationships, Mermaid syntax, and chart data in a single LLM call.

**Returns:** `dict` with the following keys:

| Key | Type | Description |
|---|---|---|
| `diagram_type` | `str` | Diagram classification |
| `description` | `str` | Detailed description of the visual content |
| `text_content` | `str` | All visible text, preserving structure |
| `elements` | `list[str]` | Identified elements/components |
| `relationships` | `list[str]` | Relationships in `"A -> B: label"` format |
| `mermaid` | `str` | Valid Mermaid diagram syntax |
| `chart_data` | `dict \| None` | Chart data with `labels`, `values`, `chart_type` (only for data charts) |

Returns an empty `dict` on failure.

### caption_frame()

```python
def caption_frame(self, image_path: Union[str, Path]) -> str
```

Get a brief 1-2 sentence caption for a frame. Used as a fallback when full diagram analysis is not warranted.

**Returns:** `str` -- a brief description of the frame content.

### process_frames()

```python
def process_frames(
    self,
    frame_paths: List[Union[str, Path]],
    diagrams_dir: Optional[Path] = None,
    captures_dir: Optional[Path] = None,
) -> Tuple[List[DiagramResult], List[ScreenCapture]]
```

Process a batch of extracted video frames through the full classification and analysis pipeline.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `frame_paths` | `List[Union[str, Path]]` | *required* | Paths to frame images |
| `diagrams_dir` | `Optional[Path]` | `None` | Output directory for diagram files (images, mermaid, JSON) |
| `captures_dir` | `Optional[Path]` | `None` | Output directory for screengrab fallback files |

**Returns:** `Tuple[List[DiagramResult], List[ScreenCapture]]`

**Confidence thresholds:**

| Confidence Range | Action |
|---|---|
| >= 0.7 | Full diagram analysis -- extracts elements, relationships, Mermaid syntax |
| 0.3 to 0.7 | Screengrab fallback -- saves frame with a brief caption |
| < 0.3 | Skipped entirely |

**Output files (when directories are provided):**

For diagrams (`diagrams_dir`):

- `diagram_N.jpg` -- original frame image
- `diagram_N.mermaid` -- Mermaid source (if generated)
- `diagram_N.json` -- full DiagramResult as JSON

For screen captures (`captures_dir`):

- `capture_N.jpg` -- original frame image
- `capture_N.json` -- ScreenCapture metadata as JSON

```python
from pathlib import Path
from video_processor.analyzers.diagram_analyzer import DiagramAnalyzer
from video_processor.providers.manager import ProviderManager

analyzer = DiagramAnalyzer(
    provider_manager=ProviderManager(),
    confidence_threshold=0.3,
)

frame_paths = list(Path("output/frames").glob("*.jpg"))
diagrams, captures = analyzer.process_frames(
    frame_paths,
    diagrams_dir=Path("output/diagrams"),
    captures_dir=Path("output/captures"),
)

print(f"Found {len(diagrams)} diagrams, {len(captures)} screengrabs")
for d in diagrams:
    print(f"  [{d.diagram_type.value}] {d.description}")
```

---

## ContentAnalyzer

```python
from video_processor.analyzers.content_analyzer import ContentAnalyzer
```

Cross-references transcript and diagram entities for richer knowledge extraction. Merges entities found in different sources and enriches key points with diagram links.

### Constructor

```python
def __init__(self, provider_manager: Optional[ProviderManager] = None)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `provider_manager` | `Optional[ProviderManager]` | `None` | Required for LLM-based fuzzy matching |

### cross_reference()

```python
def cross_reference(
    self,
    transcript_entities: List[Entity],
    diagram_entities: List[Entity],
) -> List[Entity]
```

Merge entities from transcripts and diagrams into a unified list with source attribution.

**Merge strategy:**

1. Index all transcript entities by lowercase name, marked with `source="transcript"`
2. Merge diagram entities: if a name matches, set `source="both"` and combine descriptions/occurrences; otherwise add as `source="diagram"`
3. If a `ProviderManager` is available, use LLM fuzzy matching to find additional matches among unmatched entities (e.g., "PostgreSQL" from transcript matching "Postgres" from diagram)

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `transcript_entities` | `List[Entity]` | Entities extracted from transcript |
| `diagram_entities` | `List[Entity]` | Entities extracted from diagrams |

**Returns:** `List[Entity]` -- merged entity list with `source` attribution.

```python
from video_processor.analyzers.content_analyzer import ContentAnalyzer
from video_processor.models import Entity

analyzer = ContentAnalyzer(provider_manager=pm)

transcript_entities = [
    Entity(name="PostgreSQL", type="technology"),
    Entity(name="Alice", type="person"),
]
diagram_entities = [
    Entity(name="Postgres", type="technology"),
    Entity(name="Redis", type="technology"),
]

merged = analyzer.cross_reference(transcript_entities, diagram_entities)
# "PostgreSQL" and "Postgres" may be fuzzy-matched and merged
```

### enrich_key_points()

```python
def enrich_key_points(
    self,
    key_points: List[KeyPoint],
    diagrams: list,
    transcript_text: str,
) -> List[KeyPoint]
```

Link key points to relevant diagrams by entity overlap. Examines word overlap between key point text and diagram elements/text content.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `key_points` | `List[KeyPoint]` | Key points to enrich |
| `diagrams` | `list` | List of `DiagramResult` objects or dicts |
| `transcript_text` | `str` | Full transcript text (reserved for future use) |

**Returns:** `List[KeyPoint]` -- key points with `related_diagrams` indices populated.

A key point is linked to a diagram when they share 2 or more words (excluding short words) between the key point text/details and the diagram's elements/text content.

---

## ActionDetector

```python
from video_processor.analyzers.action_detector import ActionDetector
```

Detects action items from transcripts and diagram content using LLM extraction with a regex pattern fallback.

### Constructor

```python
def __init__(self, provider_manager: Optional[ProviderManager] = None)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `provider_manager` | `Optional[ProviderManager]` | `None` | Required for LLM-based extraction |

### detect_from_transcript()

```python
def detect_from_transcript(
    self,
    text: str,
    segments: Optional[List[TranscriptSegment]] = None,
) -> List[ActionItem]
```

Detect action items from transcript text.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `text` | `str` | *required* | Transcript text to analyze |
| `segments` | `Optional[List[TranscriptSegment]]` | `None` | Transcript segments for timestamp attachment |

**Returns:** `List[ActionItem]` -- detected action items with `source="transcript"`.

**Extraction modes:**

- **LLM mode** (when `provider_manager` is set): Sends the transcript to the LLM with a structured extraction prompt. Extracts action, assignee, deadline, priority, and context.
- **Pattern mode** (fallback): Matches sentences against regex patterns for action-oriented language.

**Pattern matching** detects sentences containing:

- "need/needs to", "should/must/shall"
- "will/going to", "action item/todo/follow-up"
- "assigned to/responsible for", "deadline/due by"
- "let's/let us", "make sure/ensure"
- "can you/could you/please"

**Timestamp attachment:** When `segments` are provided, each action item is matched to the most relevant transcript segment (by word overlap, minimum 3 matching words), and a timestamp is added to `context`.

### detect_from_diagrams()

```python
def detect_from_diagrams(self, diagrams: list) -> List[ActionItem]
```

Extract action items from diagram text content and elements. Processes each diagram's combined text using either LLM or pattern extraction.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `diagrams` | `list` | List of `DiagramResult` objects or dicts |

**Returns:** `List[ActionItem]` -- action items with `source="diagram"`.

### merge_action_items()

```python
def merge_action_items(
    self,
    transcript_items: List[ActionItem],
    diagram_items: List[ActionItem],
) -> List[ActionItem]
```

Merge action items from multiple sources, deduplicating by action text (case-insensitive, whitespace-normalized).

**Returns:** `List[ActionItem]` -- deduplicated merged list.

### Usage example

```python
from video_processor.analyzers.action_detector import ActionDetector
from video_processor.providers.manager import ProviderManager

detector = ActionDetector(provider_manager=ProviderManager())

# From transcript
transcript_items = detector.detect_from_transcript(
    text="Alice needs to update the API docs by Friday. "
         "Bob should review the PR before merging.",
    segments=transcript_segments,
)

# From diagrams
diagram_items = detector.detect_from_diagrams(diagram_results)

# Merge and deduplicate
all_items = detector.merge_action_items(transcript_items, diagram_items)

for item in all_items:
    print(f"[{item.priority or 'unset'}] {item.action}")
    if item.assignee:
        print(f"  Assignee: {item.assignee}")
    if item.deadline:
        print(f"  Deadline: {item.deadline}")
```

### Pattern fallback (no LLM)

```python
# Works without any API keys
detector = ActionDetector()  # No provider_manager
items = detector.detect_from_transcript(
    "We need to finalize the database schema. "
    "Please update the deployment scripts."
)
# Returns ActionItems matched by regex patterns
```
