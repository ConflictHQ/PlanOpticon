"""Actual processing/store/export boundaries with synthetic source content."""

import json
import sqlite3
from copy import deepcopy

import pytest

from video_processor.evidence import file_revision, file_source_id, observation
from video_processor.exchange import PlanOpticonExchange
from video_processor.exporters.conflict_kg import (
    to_conflict_kg,
    write_conflict_kg_json,
    write_conflict_kg_sqlite,
)
from video_processor.integrators.graph_query import GraphQueryEngine
from video_processor.integrators.graph_store import InMemoryStore, SQLiteStore
from video_processor.integrators.knowledge_graph import KnowledgeGraph
from video_processor.models import EvidenceLocator
from video_processor.pipeline import process_single_video
from video_processor.processors.ingest import ingest_file

TEXT = "AlphaPlatform uses BetaStore."


class Provider:
    """Only the external model response is replaced; extraction and stores run."""

    def chat(self, *args, **kwargs):
        return json.dumps(
            {
                "entities": [
                    {"name": "AlphaPlatform", "type": "technology"},
                    {"name": "BetaStore", "type": "technology"},
                ],
                "relationships": [
                    {
                        "source": "AlphaPlatform",
                        "target": "BetaStore",
                        "type": "uses",
                        "confidence": 0.75,
                    }
                ],
            }
        )


def source_file(root, name="recording.mp4", content=b"synthetic recording"):
    path = root / name
    path.write_bytes(content)
    revision = file_revision(path)
    return path, {
        "source_id": file_source_id(path, revision),
        "source_type": "video",
        "title": name,
        "path": str(path),
        "ingested_at": "2026-09-25T00:00:00Z",
        "metadata": {"sha256": revision},
    }


def recording_graph(store, source):
    kg = KnowledgeGraph(provider_manager=Provider(), store=store)
    kg.register_source(source)
    source_id = source["source_id"]
    kg.process_transcript(
        {
            "segments": [
                {"start": 0.0, "end": 2.5, "text": TEXT},
                {"start": 2.5, "end": 5.0, "text": TEXT},
            ]
        },
        source_id=source_id,
    )
    kg.process_diagrams(
        [
            {
                "frame_index": 7,
                "timestamp": 3.0,
                "image_path": "diagrams/0.jpg",
                "confidence": 0.6,
                "text_content": TEXT,
            }
        ],
        source_id=source_id,
    )
    kg.process_screenshots(
        [
            {
                "frame_index": 9,
                "image_path": "captures/0.jpg",
                "confidence": 0.3,
                "text_content": TEXT,
                "entities": ["AlphaPlatform"],
            }
        ],
        source_id=source_id,
    )
    return kg


def evidence_set(kg):
    return {json.dumps(row["evidence"], sort_keys=True) for row in kg.to_dict()["relationships"]}


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_actual_multimodal_paths_and_roundtrips(tmp_path, backend):
    _, source = source_file(tmp_path)
    store = InMemoryStore() if backend == "memory" else SQLiteStore(tmp_path / "input.db")
    kg = recording_graph(store, source)
    document = tmp_path / "notes.md"
    document.write_text("# Design\n\n" + TEXT)
    assert ingest_file(document, kg) == 1
    evidence = [row["evidence"] for row in kg.to_dict()["relationships"]]
    assert {row["modality"] for row in evidence} == {
        "transcript",
        "diagram",
        "screenshot",
        "document",
    }
    by = {row["modality"]: row for row in evidence}
    assert by["transcript"]["locator"] == {
        "timestamp": 0.0,
        "end_timestamp": 5.0,
        "segment_start": 0,
        "segment_end": 1,
    }
    assert by["diagram"]["locator"]["frame_index"] == 7
    assert by["diagram"]["locator"]["image_path"] == "diagrams/0.jpg"
    assert by["diagram"]["locator"]["frame_index_basis"] == "analysis_input"
    assert by["diagram"]["detector_confidence"] == 0.6
    assert by["screenshot"]["detector_confidence"] == 0.3
    assert "timestamp" not in by["screenshot"]["locator"]
    assert by["document"]["locator"]["section"] == "Design"
    assert "page" not in by["document"]["locator"]
    for row in evidence:
        assert row["basis"] == "extraction_context"
        assert row["source_revision"] == file_revision(row["source_record"]["path"])
    assert len(store.get_entity_provenance("AlphaPlatform")) >= 4
    assert all(row["confidence"] == 0.75 for row in kg.to_dict()["relationships"])
    expected = evidence_set(kg)
    saved = kg.save(tmp_path / "graph.json")
    loaded = KnowledgeGraph.from_dict(json.loads(saved.read_text()))
    assert evidence_set(loaded) == expected
    queried = GraphQueryEngine.from_json_path(saved)
    assert {
        json.dumps(row["evidence"], sort_keys=True) for row in queried.store.get_all_relationships()
    } == expected
    saved_db = loaded.save(tmp_path / "copied.db")
    reopened = KnowledgeGraph(store=SQLiteStore(saved_db))
    assert evidence_set(reopened) == expected
    assert len(reopened._store.get_entity_provenance("AlphaPlatform")) >= 4
    exchange = PlanOpticonExchange.from_knowledge_graph(kg.to_dict(), project_name="Fixture")
    serialized = PlanOpticonExchange.model_validate_json(exchange.model_dump_json())
    assert {
        json.dumps(row.evidence.model_dump(mode="json", exclude_none=True), sort_keys=True)
        for row in serialized.relationships
    } == expected
    store.close() if isinstance(store, SQLiteStore) else None
    reopened._store.close()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_colliding_recording_labels_and_repeat_merge_preserve_every_observation(tmp_path, backend):
    _, first = source_file(tmp_path, "a.mp4", b"recording A")
    _, second = source_file(tmp_path, "b.mp4", b"recording B")
    store = InMemoryStore() if backend == "memory" else SQLiteStore(tmp_path / "merged.db")
    left = recording_graph(store, first)
    right = recording_graph(InMemoryStore(), second)
    expected = evidence_set(left) | evidence_set(right)
    left.merge(right)
    merged = left.to_dict()
    left.merge(right)
    assert left.to_dict() == merged
    assert evidence_set(left) == expected and len(expected) == 6
    exported = to_conflict_kg(merged)
    edge = next(edge for edge in exported["edges"] if edge["type"] == "uses")
    assert len(edge["props"]["observations"]) == 6
    assert {
        item["evidence"]["source_record"]["source_id"] for item in edge["props"]["observations"]
    } == {
        first["source_id"],
        second["source_id"],
    }
    assert edge["props"]["evidence_status"] == "source_qualified"
    assert edge["props"]["confidence"] == 0.75
    assert {
        item["evidence"].get("detector_confidence") for item in edge["props"]["observations"]
    } == {None, 0.3, 0.6}
    j = write_conflict_kg_json(merged, tmp_path / "conflict.json")
    db = write_conflict_kg_sqlite(merged, tmp_path / "conflict.db")
    payload = json.loads(j.read_text())
    with sqlite3.connect(db) as connection:
        actual = [
            (row[0], row[1], row[2], json.loads(row[3]))
            for row in connection.execute("SELECT source,target,type,props FROM edges")
        ]
    assert actual == [
        (row["source"], row["target"], row["type"], row["props"]) for row in payload["edges"]
    ]
    if isinstance(store, SQLiteStore):
        store.close()


def test_changed_source_revision_gets_distinct_identity_and_cannot_reuse_explicit_id(tmp_path):
    path, first = source_file(tmp_path)
    kg = recording_graph(InMemoryStore(), first)
    path.write_bytes(b"changed recording bytes")
    revision = file_revision(path)
    assert file_source_id(path, revision) != first["source_id"]
    second = deepcopy(first)
    second["metadata"]["sha256"] = revision
    before = kg.to_dict()
    other = recording_graph(InMemoryStore(), second)
    with pytest.raises(ValueError, match="different.*revision"):
        kg.merge(other)
    assert kg.to_dict() == before


@pytest.mark.parametrize(
    "locator",
    [
        {"timestamp": -1.0},
        {"timestamp": float("nan")},
        {"timestamp": True},
        {"timestamp": 4.0, "end_timestamp": 2.0},
        {"frame_index": -1},
        {"frame_index": True},
        {"page": 0},
        {"line_start": 5, "line_end": 2},
        {"segment_start": 3, "segment_end": 1},
        {"actor": "owner"},
    ],
)
def test_malformed_locators_refused(locator):
    with pytest.raises(ValueError):
        EvidenceLocator.model_validate(locator)


def test_malformed_later_locator_is_refused_before_graph_writes(tmp_path):
    _, source = source_file(tmp_path)
    kg = KnowledgeGraph(provider_manager=Provider())
    kg.register_source(source)
    with pytest.raises(ValueError):
        kg.process_diagrams(
            [{"frame_index": 1, "text_content": TEXT}, {"frame_index": -1, "text_content": TEXT}],
            source_id=source["source_id"],
        )
    assert kg.to_dict()["nodes"] == [] and kg.to_dict()["relationships"] == []


def test_document_extent_survives_the_same_storage_and_export_path(tmp_path):
    _, source = source_file(tmp_path, "pages.txt", TEXT.encode())
    source["source_type"] = "document"
    context = observation(
        source,
        "document",
        {"page": 2, "section": "Design", "line_start": 11, "line_end": 13, "chunk_index": 4},
    )
    kg = KnowledgeGraph(provider_manager=Provider(), store=SQLiteStore(tmp_path / "document.db"))
    kg.register_source(source)
    kg.add_content(TEXT, source["source_id"] + "/chunk:4", evidence=context)
    edge = to_conflict_kg(KnowledgeGraph.from_dict(kg.to_dict()).to_dict())["edges"][0]
    assert edge["props"]["observations"][0]["evidence"]["locator"] == context["locator"]
    kg._store.close()


def test_unknown_confidence_is_not_reported_as_certainty():
    out = to_conflict_kg(
        {
            "nodes": [],
            "relationships": [
                {"source": "a", "target": "b", "type": "uses"},
                {"source": "a", "target": "b", "type": "uses", "confidence": 0.4},
            ],
        }
    )
    props = out["edges"][0]["props"]
    assert props["confidence"] is None and props["evidence_status"] == "legacy_unqualified"
    assert {item["confidence"] for item in props["observations"]} == {None, 0.4}


@pytest.mark.parametrize("state", ["changed", "unqualified"])
def test_pipeline_refuses_unqualified_or_stale_cached_artifacts(tmp_path, state):
    path, source = source_file(tmp_path)
    out = tmp_path / "output"
    out.mkdir()
    (out / "cached.txt").write_text("older extraction")
    if state == "changed":
        (out / ".source-revision.json").write_text(
            json.dumps(
                {
                    "path": str(path.resolve()),
                    "sha256": source["metadata"]["sha256"],
                }
            )
        )
        path.write_bytes(b"changed source")
    with pytest.raises(ValueError, match="source revision|input revision"):
        process_single_video(path, out, provider_manager=Provider())
    assert (out / "cached.txt").read_text() == "older extraction"


def test_existing_sqlite_rows_survive_additive_migration(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(SQLiteStore._SCHEMA)
        connection.execute(
            "INSERT INTO entities(name,name_lower,type) "
            "VALUES ('AlphaPlatform','alphaplatform','technology')"
        )
        connection.execute(
            "INSERT INTO occurrences(entity_name_lower,source,timestamp,text) "
            "VALUES ('alphaplatform','transcript_batch_0',1.5,'legacy input')"
        )
        connection.execute(
            "INSERT INTO relationships(source,target,type,content_source,timestamp) "
            "VALUES ('AlphaPlatform','BetaStore','uses','transcript_batch_0',1.5)"
        )
    store = SQLiteStore(path)
    assert store.get_entity("AlphaPlatform")["occurrences"] == [
        {"source": "transcript_batch_0", "timestamp": 1.5, "text": "legacy input"},
    ]
    props = to_conflict_kg(store.to_dict())["edges"][0]["props"]
    assert props["evidence_status"] == "legacy_unqualified"
    assert props["confidence"] is None
    assert props["observations"][0]["timestamp"] == 1.5
    store.close()


def test_explicit_source_revision_mismatch_does_not_write_claims(tmp_path):
    _, source = source_file(tmp_path)
    context = observation(source, "transcript", {"timestamp": 1.0})
    context["source_revision"] = "0" * 64
    kg = KnowledgeGraph(provider_manager=Provider())
    with pytest.raises(ValueError, match="differs"):
        kg.add_content(TEXT, "source", evidence=context)
    assert kg.to_dict() == {"nodes": [], "relationships": []}


def test_qualified_diagrams_from_similarly_named_sources_do_not_fuzzy_merge(tmp_path):
    _, first = source_file(tmp_path, "a.mp4", b"a")
    _, second = source_file(tmp_path, "b.mp4", b"b")
    first["source_id"], second["source_id"] = "recording-a", "recording-b"
    left = recording_graph(InMemoryStore(), first)
    left.merge(recording_graph(InMemoryStore(), second))
    assert len([node for node in left.to_dict()["nodes"] if node["type"] == "diagram"]) == 2


def test_exchange_merge_preserves_distinct_observations_and_rejects_revision_reuse(tmp_path):
    _, first_source = source_file(tmp_path, "one.mp4")
    _, second_source = source_file(tmp_path, "two.mp4")
    first = recording_graph(InMemoryStore(), first_source)
    second = recording_graph(InMemoryStore(), second_source)
    left = PlanOpticonExchange.from_knowledge_graph(first.to_dict())
    right = PlanOpticonExchange.from_knowledge_graph(second.to_dict())
    left.merge(right)
    left.merge(right)
    assert len(left.relationships) == 6
    alpha = next(e for e in left.entities if e.name == "AlphaPlatform")
    assert {o["evidence"]["source_record"]["source_id"] for o in alpha.occurrences} == {
        first_source["source_id"],
        second_source["source_id"],
    }
    before = left.model_dump()
    changed = right.model_copy(deep=True)
    changed.sources[0].metadata["sha256"] = "b" * 64
    with pytest.raises(ValueError, match="source identity"):
        left.merge(changed)
    assert left.model_dump() == before


def test_estimated_transcript_timing_is_not_evidence(tmp_path):
    _, source = source_file(tmp_path)
    kg = KnowledgeGraph(provider_manager=Provider())
    kg.register_source(source)
    kg.process_transcript(
        {
            "segments": [
                {
                    "text": TEXT,
                    "start": 2.0,
                    "end": 5.0,
                    "timing_basis": "estimated",
                }
            ]
        },
        source_id=source["source_id"],
    )
    rel = kg.to_dict()["relationships"][0]
    assert rel["timestamp"] is None
    assert rel["evidence"]["locator"] == {"segment_start": 0, "segment_end": 0}


def test_pipeline_resumes_both_visual_modalities_with_real_store(tmp_path):
    import wave

    from PIL import Image

    from video_processor.output_structure import create_video_output_dirs
    from video_processor.utils.usage_tracker import UsageTracker

    class PipelineProvider(Provider):
        usage = UsageTracker()

        def transcribe_audio(self, *args, **kwargs):
            return {"text": TEXT, "duration": 1.0}

        def get_models_used(self):
            return {}

    path, source = source_file(tmp_path)
    out = tmp_path / "output"
    dirs = create_video_output_dirs(out, path.stem)
    (out / ".source-revision.json").write_text(
        json.dumps(
            {
                "path": str(path.resolve()),
                "sha256": source["metadata"]["sha256"],
            }
        )
    )
    Image.new("RGB", (8, 8)).save(dirs["frames"] / "frame_0000.jpg")
    (out / "audio").mkdir()
    with wave.open(str(out / "audio" / f"{path.stem}.wav"), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000)
    (dirs["results"] / "visual-analysis.json").write_text(
        json.dumps(
            {
                "diagrams": [{"frame_index": 0, "text_content": TEXT}],
                "captures": [{"frame_index": 1, "text_content": TEXT}],
            }
        )
    )
    (dirs["results"] / "analysis.md").write_text("# Synthetic cached analysis")
    for name in ("key_points.json", "action_items.json"):
        (dirs["results"] / name).write_text("[]")
    for _ in range(2):
        manifest = process_single_video(path, out, provider_manager=PipelineProvider())
        assert manifest.stats.diagrams_detected == 1
        assert manifest.stats.screen_captures == 1
        graph = json.loads((dirs["results"] / "knowledge_graph.json").read_text())
        assert len(graph["relationships"]) == 3
        by = {r["evidence"]["modality"]: r["evidence"] for r in graph["relationships"]}
        assert set(by) == {"transcript", "diagram", "screenshot"}
        assert by["transcript"]["locator"].get("timestamp") is None
        assert by["diagram"].get("detector_confidence") is None
        assert graph["sources"][0]["metadata"]["graph_complete"] is True
