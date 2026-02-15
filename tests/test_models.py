"""Tests for pydantic data models."""

from video_processor.models import (
    ActionItem,
    BatchManifest,
    BatchVideoEntry,
    DiagramResult,
    DiagramType,
    Entity,
    KeyPoint,
    KnowledgeGraphData,
    OutputFormat,
    ProcessingStats,
    Relationship,
    ScreenCapture,
    TranscriptSegment,
    VideoManifest,
    VideoMetadata,
)


class TestEnums:
    def test_diagram_type_values(self):
        assert DiagramType.flowchart == "flowchart"
        assert DiagramType.unknown == "unknown"
        assert len(DiagramType) == 9

    def test_output_format_values(self):
        assert OutputFormat.markdown == "markdown"
        assert OutputFormat.pdf == "pdf"
        assert len(OutputFormat) == 6


class TestTranscriptSegment:
    def test_basic(self):
        seg = TranscriptSegment(start=0.0, end=5.0, text="Hello world")
        assert seg.start == 0.0
        assert seg.speaker is None

    def test_round_trip(self):
        seg = TranscriptSegment(start=1.0, end=2.0, text="Hi", speaker="Alice", confidence=0.95)
        restored = TranscriptSegment.model_validate_json(seg.model_dump_json())
        assert restored == seg


class TestActionItem:
    def test_minimal(self):
        item = ActionItem(action="Fix the bug")
        assert item.assignee is None
        assert item.priority is None

    def test_full(self):
        item = ActionItem(
            action="Deploy to prod",
            assignee="Bob",
            deadline="Friday",
            priority="high",
            context="After QA passes",
            source="transcript",
        )
        restored = ActionItem.model_validate_json(item.model_dump_json())
        assert restored == item


class TestKeyPoint:
    def test_with_related_diagrams(self):
        kp = KeyPoint(
            point="System uses microservices", topic="Architecture", related_diagrams=[0, 2]
        )
        assert kp.related_diagrams == [0, 2]

    def test_round_trip(self):
        kp = KeyPoint(point="Test", details="Detail", timestamp=42.0, source="diagram")
        restored = KeyPoint.model_validate_json(kp.model_dump_json())
        assert restored == kp


class TestDiagramResult:
    def test_defaults(self):
        dr = DiagramResult(frame_index=0)
        assert dr.diagram_type == DiagramType.unknown
        assert dr.confidence == 0.0
        assert dr.chart_data is None
        assert dr.elements == []

    def test_chart_data(self):
        dr = DiagramResult(
            frame_index=5,
            diagram_type=DiagramType.chart,
            confidence=0.9,
            chart_data={"labels": ["A", "B"], "values": [10, 20], "chart_type": "bar"},
        )
        restored = DiagramResult.model_validate_json(dr.model_dump_json())
        assert restored.chart_data["chart_type"] == "bar"

    def test_full_round_trip(self):
        dr = DiagramResult(
            frame_index=3,
            timestamp=15.5,
            diagram_type=DiagramType.flowchart,
            confidence=0.85,
            description="Login flow",
            text_content="Start -> Auth -> Dashboard",
            elements=["Start", "Auth", "Dashboard"],
            relationships=["Start->Auth", "Auth->Dashboard"],
            mermaid="graph LR\n    A-->B-->C",
            image_path="diagrams/diagram_3.jpg",
            svg_path="diagrams/diagram_3.svg",
            png_path="diagrams/diagram_3.png",
            mermaid_path="diagrams/diagram_3.mermaid",
        )
        restored = DiagramResult.model_validate_json(dr.model_dump_json())
        assert restored == dr


class TestScreenCapture:
    def test_basic(self):
        sc = ScreenCapture(frame_index=10, caption="Architecture overview slide", confidence=0.5)
        assert sc.image_path is None

    def test_round_trip(self):
        sc = ScreenCapture(
            frame_index=7,
            timestamp=30.0,
            caption="Timeline",
            image_path="captures/capture_0.jpg",
            confidence=0.45,
        )
        restored = ScreenCapture.model_validate_json(sc.model_dump_json())
        assert restored == sc


class TestEntity:
    def test_defaults(self):
        e = Entity(name="Python")
        assert e.type == "concept"
        assert e.descriptions == []
        assert e.occurrences == []

    def test_round_trip(self):
        e = Entity(
            name="Alice",
            type="person",
            descriptions=["Team lead", "Engineer"],
            source="both",
            occurrences=[{"source": "transcript", "timestamp": 5.0, "text": "Alice said..."}],
        )
        restored = Entity.model_validate_json(e.model_dump_json())
        assert restored == e


class TestKnowledgeGraphData:
    def test_empty(self):
        kg = KnowledgeGraphData()
        assert kg.nodes == []
        assert kg.relationships == []

    def test_round_trip(self):
        kg = KnowledgeGraphData(
            nodes=[Entity(name="A"), Entity(name="B")],
            relationships=[Relationship(source="A", target="B", type="depends_on")],
        )
        restored = KnowledgeGraphData.model_validate_json(kg.model_dump_json())
        assert len(restored.nodes) == 2
        assert restored.relationships[0].type == "depends_on"


class TestVideoManifest:
    def test_minimal(self):
        m = VideoManifest(video=VideoMetadata(title="Test Video"))
        assert m.version == "1.0"
        assert m.diagrams == []
        assert m.screen_captures == []
        assert m.stats.frames_extracted == 0

    def test_full_round_trip(self):
        m = VideoManifest(
            video=VideoMetadata(
                title="Meeting", source_path="/tmp/video.mp4", duration_seconds=3600.0
            ),
            stats=ProcessingStats(
                frames_extracted=50,
                diagrams_detected=3,
                screen_captures=2,
                models_used={"vision": "gpt-4o", "chat": "claude-sonnet-4-5"},
            ),
            transcript_json="transcript/transcript.json",
            analysis_md="results/analysis.md",
            key_points=[KeyPoint(point="Important thing")],
            action_items=[ActionItem(action="Do the thing")],
            diagrams=[DiagramResult(frame_index=0, confidence=0.9)],
            screen_captures=[ScreenCapture(frame_index=5, caption="Slide")],
            frame_paths=["frames/frame_0000.jpg", "frames/frame_0001.jpg"],
        )
        json_str = m.model_dump_json()
        restored = VideoManifest.model_validate_json(json_str)
        assert restored.video.title == "Meeting"
        assert len(restored.diagrams) == 1
        assert len(restored.screen_captures) == 1
        assert restored.stats.models_used["vision"] == "gpt-4o"


class TestBatchManifest:
    def test_minimal(self):
        m = BatchManifest()
        assert m.total_videos == 0
        assert m.videos == []

    def test_full_round_trip(self):
        m = BatchManifest(
            title="Weekly Meetings",
            total_videos=3,
            completed_videos=2,
            failed_videos=1,
            total_diagrams=5,
            total_action_items=10,
            total_key_points=15,
            videos=[
                BatchVideoEntry(
                    video_name="meeting_1",
                    manifest_path="videos/meeting_1/manifest.json",
                    status="completed",
                    diagrams_count=3,
                    action_items_count=5,
                ),
                BatchVideoEntry(
                    video_name="meeting_2",
                    manifest_path="videos/meeting_2/manifest.json",
                    status="failed",
                    error="Audio extraction failed",
                ),
            ],
            batch_summary_md="batch_summary.md",
            merged_knowledge_graph_json="knowledge_graph.json",
        )
        json_str = m.model_dump_json()
        restored = BatchManifest.model_validate_json(json_str)
        assert restored.total_videos == 3
        assert restored.videos[1].status == "failed"
        assert restored.videos[1].error == "Audio extraction failed"
