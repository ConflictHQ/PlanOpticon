"""Producer conformance (#153) — the conflict-kg/v1 exporter emits the
supergraph contract v1.0 ADDITIVELY: the shape the brain's consumers already
read (ids = lowercased names, occurrences for provenance) is unchanged, and the
contract rides beside it."""

import json

from video_processor.exporters.conflict_kg import (
    ADDRESS_KIND,
    CONTRACT_VERSION,
    PRODUCER,
    REALM,
    address_for,
    to_conflict_kg,
    write_conflict_kg_json,
    write_conflict_kg_sqlite,
)


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
    conn.close()
