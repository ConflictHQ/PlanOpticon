"""Producer conformance (#153) — the conflict-kg/v1 exporter emits the
supergraph contract v1.0 ADDITIVELY: the shape the brain's consumers already
read (ids = lowercased names, occurrences for provenance) is unchanged, and the
contract rides beside it."""

import json

from video_processor.exporters.conflict_kg import (
    ADDRESS_KIND,
    CONTRACT_VERSION,
    EDGE_VERBS,
    PRODUCER,
    REALM,
    address_for,
    canonical_edge_type,
    to_conflict_kg,
    write_conflict_kg_json,
    write_conflict_kg_sqlite,
)

# The consuming brain's declared edge vocabulary (project-brain
# template/brain-schema.json `edges`, contract 1.0): every emitted type is one.
BRAIN_EDGES = {
    "contains",
    "about",
    "decided_in",
    "references",
    "relates_to",
    "uses",
    "provides",
    "integrates_with",
    "owns",
    "escalates_to",
    "implemented_in",
    "in_repo",
    "supersedes",
    "contradicts",
    "tagged_with",
    "broader",
    "same_as",
    "facet_of",
    "aligns_with",
    "asserted_by",
    "affiliated_with",
    "raised_in",
    "other",
    "depends_on",
    "derives_from",
    "child_of",
    "blocked_by",
    "critical_path",
    "member_of",
    "has_entity",
    "has_field",
    "in_catalog",
}


def _kg():
    return {
        "nodes": [
            {
                "name": "Acme Corp",
                "type": "organization",
                "descriptions": ["A client"],
                "occurrences": [{"recording": "kickoff", "text": "..."}],
            },
            {"name": "Data Platform", "type": "project"},
        ],
        "relationships": [
            {
                "source": "Acme Corp",
                "target": "Data Platform",
                "type": "owns",
                "content_source": "kickoff",
            },
            {"source": "Data Platform", "target": "Acme Corp", "type": "serves", "confidence": 0.7},
        ],
    }


def test_envelope_declares_version_realm_producer():
    out = to_conflict_kg(_kg())
    assert out["format"] == "conflict-kg/v1"
    assert out["contract"] == {
        "version": CONTRACT_VERSION,
        "realm": REALM,
        "producer": PRODUCER,
        "address_kind": ADDRESS_KIND,
    }
    assert out["contract"]["version"] == "1.0" and out["contract"]["realm"] == "brain"


def test_ids_unchanged_and_address_added():
    out = to_conflict_kg(_kg())
    n = {x["id"]: x for x in out["nodes"]}
    assert set(n) == {"acme corp", "data platform"}  # consumer identity key intact
    assert n["acme corp"]["props"]["address"] == "kg-entity:acme-corp"
    assert n["acme corp"]["props"]["occurrences"][0]["recording"] == "kickoff"  # provenance intact


def test_repo_namespaces_addresses():
    out = to_conflict_kg(_kg(), repo="sales")
    assert out["contract"]["repo"] == "sales"
    assert out["nodes"][0]["props"]["address"] == "sales/kg-entity:acme-corp"
    assert address_for("Acme Corp", "sales") == "sales/kg-entity:acme-corp"


def test_every_edge_is_attested():
    out = to_conflict_kg(_kg())
    for e in out["edges"]:
        assert e["props"]["asserted_by"] == "planopticon"
        assert 0.0 <= e["props"]["confidence"] <= 1.0
    by = {(e["source"], e["target"]): e for e in out["edges"]}
    assert by[("acme corp", "data platform")]["props"]["confidence"] == 1.0
    assert by[("acme corp", "data platform")]["props"]["content_source"] == "kickoff"
    assert by[("data platform", "acme corp")]["props"]["confidence"] == 0.7


def test_json_and_sqlite_encodings_carry_conformant_props(tmp_path):
    j = write_conflict_kg_json(_kg(), tmp_path / "kg.json")
    data = json.loads(j.read_text())
    assert data["contract"]["producer"] == "planopticon"
    db = write_conflict_kg_sqlite(_kg(), tmp_path / "kg.db")
    import sqlite3

    conn = sqlite3.connect(db)
    props = json.loads(conn.execute("SELECT props FROM nodes WHERE id='acme corp'").fetchone()[0])
    assert props["address"] == "kg-entity:acme-corp"
    eprops = json.loads(conn.execute("SELECT props FROM edges LIMIT 1").fetchone()[0])
    assert eprops["asserted_by"] == "planopticon"
    assert eprops["sources"] == ["kickoff"] and eprops["raw_types"] == ["owns"]
    conn.close()


def _edges(*relationships):
    nodes = [{"name": n, "type": "concept"} for n in ("Alice", "Payroll", "QuickBooks")]
    return to_conflict_kg({"nodes": nodes, "relationships": list(relationships)})["edges"]


def test_mapping_targets_only_extraction_facing_declared_edges():
    targets = set(EDGE_VERBS.values())
    assert targets <= BRAIN_EDGES
    assert targets == {
        "uses",
        "provides",
        "integrates_with",
        "relates_to",
        "about",
        "contains",
        "broader",
        "other",
    }
    # An extracted verb that happens to spell a structural id (a doc link, a
    # stakeholder's ownership, work ordering, a code-realm join, identity) is
    # still only an unclassified extraction relation.
    for verb in ("references", "owns", "depends_on", "implemented_in", "same_as"):
        assert canonical_edge_type(verb) == "other"


def test_free_verbs_canonicalize_and_keep_the_extracted_verb():
    edges = _edges(
        {"source": "QuickBooks", "target": "Payroll", "type": "feeds into"},
        {"source": "Payroll", "target": "QuickBooks", "type": "integrated into"},
        {"source": "Payroll", "target": "QuickBooks", "type": "no integration"},
        {"source": "Alice", "target": "Payroll", "type": "Is  Associated With"},
        {"source": "Alice", "target": "QuickBooks", "type": "related_to"},
        {"source": "Alice", "target": "Payroll", "type": "manages"},
    )
    by = {(e["source"], e["target"], e["type"]): e["props"].get("raw_types") for e in edges}
    assert by == {
        ("quickbooks", "payroll", "provides"): ["feeds into"],
        ("payroll", "quickbooks", "integrates_with"): ["integrated into"],
        ("payroll", "quickbooks", "other"): ["no integration"],  # exact match, not substring
        ("alice", "payroll", "relates_to"): ["Is  Associated With"],
        ("alice", "quickbooks", "relates_to"): ["related_to"],  # the store's default verb
        ("alice", "payroll", "other"): ["manages"],  # no declared equivalent
    }
    assert {e["type"] for e in edges} <= BRAIN_EDGES


def test_raw_types_only_when_the_extracted_verb_is_not_the_type():
    edges = _edges(
        {"source": "Alice", "target": "QuickBooks", "type": "uses"},
        {"source": "Payroll", "target": "QuickBooks", "type": "integrates_with"},
        {"source": "Alice", "target": "Payroll", "type": "Uses"},
    )
    assert [(e["type"], e["props"].get("raw_types")) for e in edges] == [
        ("uses", None),  # already the declared id: nothing to audit
        ("integrates_with", None),
        ("uses", ["Uses"]),  # a spelling variant is still a rewrite, so it is kept
    ]


def test_canonicalization_is_idempotent():
    for edge_type in set(EDGE_VERBS.values()):
        assert canonical_edge_type(edge_type) == edge_type
    once = to_conflict_kg(_kg())  # owns / serves have no extraction-facing equivalent
    assert [e["type"] for e in once["edges"]] == ["other", "other"]
    again = to_conflict_kg({"nodes": _kg()["nodes"], "relationships": once["edges"]})
    assert [e["type"] for e in again["edges"]] == ["other", "other"]
    assert all("raw_types" not in e["props"] for e in again["edges"])


def test_repeated_observations_merge_into_one_multiply_attested_edge():
    edges = _edges(
        {
            "source": "Alice",
            "target": "QuickBooks",
            "type": "uses",
            "content_source": "transcript_batch_0",
            "timestamp": 12.0,
        },
        {
            "source": "alice",
            "target": "QuickBooks",
            "type": "utilizes",
            "content_source": "diagram_2",
        },
        {
            "source": "Alice",
            "target": "QuickBooks",
            "type": "uses",
            "content_source": "transcript_batch_10",
            "timestamp": 340.0,
        },
        {
            "source": "Alice",
            "target": "QuickBooks",
            "type": "uses",
            "content_source": "transcript_batch_0",
        },
        {"source": "QuickBooks", "target": "Alice", "type": "uses", "content_source": "diagram_2"},
        {"source": "Alice", "target": "QuickBooks", "type": "manages"},
    )
    assert [(e["source"], e["target"], e["type"]) for e in edges] == [
        ("alice", "quickbooks", "uses"),
        ("quickbooks", "alice", "uses"),  # direction is part of the edge
        ("alice", "quickbooks", "other"),  # a different relation between the same pair
    ]
    assert edges[0]["props"] == {
        "asserted_by": "planopticon",
        "confidence": 1.0,
        "content_source": "transcript_batch_0",  # scalar props: the first observation's
        "timestamp": 12.0,
        "sources": ["diagram_2", "transcript_batch_0", "transcript_batch_10"],
        "raw_types": ["uses", "utilizes"],
    }
    assert edges[1]["props"]["sources"] == ["diagram_2"]
    assert "sources" not in edges[2]["props"]  # no content source recorded, none invented
