"""Tests for the template-based markdown/CSV document generators.

No LLM involved — every generator is a pure function of a knowledge-graph
dict, so each test asserts on the actual rendered content (headings, entity
names, table rows, CSV parsing, Mermaid edges) for both a populated graph and
the empty-graph path.
"""

import csv
import io

from video_processor.exporters.markdown import (
    DOCUMENT_TYPES,
    generate_all,
    generate_csv_export,
    generate_entity_brief,
    generate_entity_index,
    generate_executive_summary,
    generate_glossary,
    generate_meeting_notes,
    generate_relationship_map,
    generate_status_report,
)


def _sample_kg():
    """A general knowledge graph (people / tech / org).

    The Python node carries an ``occurrences`` entry so the entity-brief
    "Sources" section and the CSV "Source" column get exercised.
    """
    return {
        "nodes": [
            {
                "name": "Python",
                "type": "technology",
                "descriptions": ["A programming language"],
                "occurrences": [
                    {"source": "meeting.mp4", "timestamp": "00:01:23", "text": "We use Python"}
                ],
            },
            {"name": "Django", "type": "technology", "descriptions": ["A web framework"]},
            {"name": "Alice", "type": "person", "descriptions": ["Software engineer"]},
            {"name": "Bob", "type": "person", "descriptions": ["Product manager"]},
            {"name": "Acme Corp", "type": "organization", "descriptions": ["A tech company"]},
        ],
        "relationships": [
            {"source": "Alice", "target": "Python", "type": "uses"},
            {"source": "Alice", "target": "Bob", "type": "works_with"},
            {"source": "Django", "target": "Python", "type": "built_on"},
            {"source": "Alice", "target": "Acme Corp", "type": "employed_by"},
        ],
    }


def _planning_kg():
    """A planning-flavoured graph exercising the milestone/feature/decision/etc.

    types that meeting-notes and status-report categorise on, plus
    ``assigned_to`` / ``owned_by`` edges that drive the action-item owners.
    """
    return {
        "nodes": [
            {"name": "Launch v1", "type": "milestone", "descriptions": ["Ship the first release"]},
            {
                "name": "Search feature",
                "type": "feature",
                "descriptions": ["Full-text search over notes"],
            },
            {
                "name": "GDPR compliance",
                "type": "requirement",
                "descriptions": ["Must comply with GDPR"],
            },
            {
                "name": "Limited budget",
                "type": "constraint",
                "descriptions": ["Only $10k available"],
            },
            {"name": "Vendor lock-in", "type": "risk", "descriptions": ["Risk of AWS lock-in"]},
            {
                "name": "Adopt Postgres",
                "type": "decision",
                "descriptions": ["Use Postgres as primary DB"],
            },
            {
                "name": "Improve onboarding",
                "type": "goal",
                "descriptions": ["Reduce time-to-first-value"],
            },
            {"name": "Carol", "type": "person", "descriptions": ["Engineering lead"]},
            {"name": "Dave", "type": "person", "descriptions": ["Designer"]},
            {
                "name": "Caching",
                "type": "concept",
                "descriptions": ["Use of caches to speed up reads"],
            },
        ],
        "relationships": [
            {"source": "Search feature", "target": "Carol", "type": "assigned_to"},
            {"source": "Improve onboarding", "target": "Dave", "type": "owned_by"},
            {"source": "Launch v1", "target": "Search feature", "type": "includes"},
        ],
    }


def _empty_kg():
    return {"nodes": [], "relationships": []}


class TestGenerateEntityBrief:
    def test_outgoing_relationships_and_summary(self):
        kg = _sample_kg()
        alice = next(n for n in kg["nodes"] if n["name"] == "Alice")
        brief = generate_entity_brief(alice, kg["relationships"])

        assert brief.startswith("# Alice")
        assert "**Type:** person" in brief
        assert "## Summary" in brief
        assert "- Software engineer" in brief
        assert "## Relates To" in brief
        assert "| Python | uses |" in brief
        assert "| Bob | works_with |" in brief
        assert "| Acme Corp | employed_by |" in brief
        # Alice never appears as a relationship target.
        assert "## Referenced By" not in brief

    def test_incoming_relationships_and_sources(self):
        kg = _sample_kg()
        python = next(n for n in kg["nodes"] if n["name"] == "Python")
        brief = generate_entity_brief(python, kg["relationships"])

        assert "## Referenced By" in brief
        assert "| Alice | uses |" in brief
        assert "| Django | built_on |" in brief
        # Python has no outgoing edges.
        assert "## Relates To" not in brief
        # occurrences render as a Sources section.
        assert "## Sources" in brief
        assert "**meeting.mp4**" in brief
        assert "00:01:23" in brief
        assert "We use Python" in brief

    def test_minimal_entity_omits_optional_sections(self):
        brief = generate_entity_brief({"name": "Solo", "type": "concept"}, [])
        assert brief.startswith("# Solo")
        assert "**Type:** concept" in brief
        assert "## Summary" not in brief
        assert "## Relates To" not in brief
        assert "## Referenced By" not in brief
        assert "## Sources" not in brief

    def test_defaults_for_missing_name_and_type(self):
        brief = generate_entity_brief({}, [])
        assert "# Untitled" in brief
        assert "**Type:** concept" in brief


class TestGenerateExecutiveSummary:
    def test_happy_path(self):
        out = generate_executive_summary(_sample_kg())
        assert out.startswith("# Executive Summary")
        assert "**5 entities**" in out
        assert "**4 relationships**" in out
        assert "**3 categories**" in out
        assert "## Entity Breakdown" in out
        # technology bucket lists its example members.
        assert "Python, Django" in out
        assert "## Key Entities (by connections)" in out
        # Alice is the most-connected entity (degree 3).
        assert "| Alice | 3 |" in out
        assert "## Relationship Types" in out

    def test_empty_graph_drops_optional_sections(self):
        out = generate_executive_summary(_empty_kg())
        assert out.startswith("# Executive Summary")
        assert "**0 entities**" in out
        assert "**0 relationships**" in out
        assert "**0 categories**" in out
        assert "## Key Entities" not in out
        assert "## Relationship Types" not in out


class TestGenerateMeetingNotes:
    def test_happy_path(self):
        out = generate_meeting_notes(_planning_kg())
        assert out.startswith("# Meeting Notes")

        assert "## Discussion Topics" in out
        assert "- **Caching**: Use of caches to speed up reads" in out

        assert "## Participants" in out
        assert "- Carol" in out
        assert "- Dave" in out

        assert "## Decisions & Constraints" in out
        assert "- **Adopt Postgres**: Use Postgres as primary DB" in out
        assert "- **Limited budget**: Only $10k available" in out

        assert "## Action Items" in out
        # Owners are resolved from assigned_to / owned_by edges.
        assert "- [ ] **Search feature** (@Carol): Full-text search over notes" in out
        assert "- [ ] **Improve onboarding** (@Dave): Reduce time-to-first-value" in out
        # A milestone with no owner edge still renders as an unchecked action.
        assert "- [ ] **Launch v1**: Ship the first release" in out

        assert "## Open Questions / Loose Ends" in out

    def test_custom_title(self):
        out = generate_meeting_notes(_planning_kg(), title="Sprint Planning")
        assert out.startswith("# Sprint Planning")

    def test_empty_graph_drops_all_sections(self):
        out = generate_meeting_notes(_empty_kg())
        assert out.startswith("# Meeting Notes")
        assert "## Discussion Topics" not in out
        assert "## Participants" not in out
        assert "## Decisions & Constraints" not in out
        assert "## Action Items" not in out
        assert "## Open Questions / Loose Ends" not in out


class TestGenerateGlossary:
    def test_happy_path(self):
        out = generate_glossary(_sample_kg())
        assert out.startswith("# Glossary")
        assert "**Acme Corp** *(organization)*" in out
        assert "**Python** *(technology)*" in out
        assert ": A programming language" in out

    def test_entries_sorted_case_insensitively(self):
        out = generate_glossary(_sample_kg())
        # Alphabetical: Acme Corp < Alice < Bob < Django < Python.
        assert out.index("Acme Corp") < out.index("Django") < out.index("Python")

    def test_missing_description_falls_back(self):
        kg = {"nodes": [{"name": "Widget", "type": "concept"}], "relationships": []}
        out = generate_glossary(kg)
        assert "**Widget** *(concept)*" in out
        assert "No description available." in out

    def test_empty_graph(self):
        out = generate_glossary(_empty_kg())
        assert out.strip() == "# Glossary"


class TestGenerateRelationshipMap:
    def test_happy_path(self):
        out = generate_relationship_map(_sample_kg())
        assert out.startswith("# Relationship Map")
        assert "*5 entities, 4 relationships*" in out
        # Relationship-type headings are title-cased with underscores spaced.
        assert "## Works With" in out
        assert "## Employed By" in out
        assert "| Alice | Bob |" in out
        # Mermaid diagram of the top-degree nodes.
        assert "```mermaid" in out
        assert "graph LR" in out
        assert 'Alice["Alice"] -->|uses| Python["Python"]' in out

    def test_empty_graph_has_no_diagram(self):
        out = generate_relationship_map(_empty_kg())
        assert out.startswith("# Relationship Map")
        assert "*0 entities, 0 relationships*" in out
        assert "```mermaid" not in out


class TestGenerateStatusReport:
    def test_happy_path(self):
        out = generate_status_report(_planning_kg())
        assert out.startswith("# Status Report")
        assert "- **Entities:** 10" in out
        assert "- **Relationships:** 3" in out
        assert "- **Features:** 1" in out
        assert "- **Milestones:** 1" in out
        assert "- **Requirements:** 1" in out
        # risk + constraint both count toward Risks/Constraints.
        assert "- **Risks/Constraints:** 2" in out

        assert "## Milestones" in out
        assert "- **Launch v1**: Ship the first release" in out
        assert "## Features" in out
        assert "| Search feature |" in out
        assert "## Risks & Constraints" in out
        assert "- **Vendor lock-in**: Risk of AWS lock-in" in out
        assert "- **Limited budget**: Only $10k available" in out

    def test_custom_title(self):
        out = generate_status_report(_planning_kg(), title="Q3 Status")
        assert out.startswith("# Q3 Status")

    def test_empty_graph(self):
        out = generate_status_report(_empty_kg())
        assert out.startswith("# Status Report")
        assert "- **Entities:** 0" in out
        assert "- **Features:** 0" in out
        assert "## Milestones" not in out
        assert "## Features" not in out
        assert "## Risks & Constraints" not in out


class TestGenerateEntityIndex:
    def test_happy_path(self):
        out = generate_entity_index(_sample_kg())
        assert out.startswith("# Entity Index")
        assert "*5 entities across 3 types*" in out
        assert "## Organization (1)" in out
        assert "## Person (2)" in out
        assert "## Technology (2)" in out
        assert "- **Alice** — Software engineer" in out

    def test_empty_graph(self):
        out = generate_entity_index(_empty_kg())
        assert out.startswith("# Entity Index")
        assert "*0 entities across 0 types*" in out


class TestGenerateCsvExport:
    def test_happy_path_parses(self):
        content = generate_csv_export(_sample_kg())
        rows = list(csv.reader(io.StringIO(content)))
        assert rows[0] == ["Name", "Type", "Description", "Related To", "Source"]
        # header + 5 entities
        assert len(rows) == 6

        by_name = {r["Name"]: r for r in csv.DictReader(io.StringIO(content))}
        assert by_name["Alice"]["Type"] == "person"
        # "Related To" preserves relationship insertion order for the source.
        assert by_name["Alice"]["Related To"] == "Python; Bob; Acme Corp"
        assert by_name["Python"]["Description"] == "A programming language"
        # Source column comes from the first occurrence.
        assert by_name["Python"]["Source"] == "meeting.mp4"
        assert by_name["Bob"]["Related To"] == ""

    def test_rows_sorted_by_name(self):
        content = generate_csv_export(_sample_kg())
        names = [r["Name"] for r in csv.DictReader(io.StringIO(content))]
        assert names == sorted(names)

    def test_empty_graph_is_header_only(self):
        content = generate_csv_export(_empty_kg())
        rows = list(csv.reader(io.StringIO(content)))
        assert len(rows) == 1
        assert rows[0] == ["Name", "Type", "Description", "Related To", "Source"]


class TestDocumentTypesRegistry:
    def test_expected_keys(self):
        assert set(DOCUMENT_TYPES) == {
            "summary",
            "meeting-notes",
            "glossary",
            "relationship-map",
            "status-report",
            "entity-index",
            "csv",
        }

    def test_every_generator_produces_nonempty_output(self):
        kg = _sample_kg()
        for label, generator in DOCUMENT_TYPES.values():
            assert isinstance(label, str) and label
            out = generator(kg)
            assert isinstance(out, str) and out.strip()


class TestGenerateAll:
    def test_writes_all_docs_and_entity_briefs(self, tmp_path):
        created = generate_all(_sample_kg(), tmp_path)
        names = {p.name for p in created}

        for fn in (
            "summary.md",
            "meeting-notes.md",
            "glossary.md",
            "relationship-map.md",
            "status-report.md",
            "entity-index.md",
            "csv.csv",
        ):
            assert (tmp_path / fn).exists()
            assert fn in names

        entities_dir = tmp_path / "entities"
        assert entities_dir.is_dir()
        # A space in the name is sanitised to a dash for the filename.
        assert (entities_dir / "Acme-Corp.md").exists()
        assert (entities_dir / "Python.md").exists()

        # Written content is real, not empty.
        assert "# Executive Summary" in (tmp_path / "summary.md").read_text()
        assert (tmp_path / "csv.csv").read_text().startswith("Name,Type,Description")

        # 7 document types + 5 entity briefs.
        assert len(created) == 12

    def test_doc_types_filter(self, tmp_path):
        created = generate_all(_sample_kg(), tmp_path, doc_types=["summary", "csv"])
        assert (tmp_path / "summary.md").exists()
        assert (tmp_path / "csv.csv").exists()
        assert not (tmp_path / "glossary.md").exists()
        # 2 selected docs + 5 entity briefs.
        assert len(created) == 7

    def test_unknown_doc_type_is_skipped(self, tmp_path):
        created = generate_all(_sample_kg(), tmp_path, doc_types=["bogus"])
        assert not (tmp_path / "bogus.md").exists()
        # No doc files, only the 5 entity briefs.
        assert len(created) == 5
        assert all(p.parent.name == "entities" for p in created)

    def test_empty_graph_writes_docs_but_no_briefs(self, tmp_path):
        created = generate_all(_empty_kg(), tmp_path)
        assert (tmp_path / "summary.md").exists()
        assert (tmp_path / "entities").is_dir()
        # 7 document types, no entity briefs.
        assert len(created) == 7

    def test_sanitises_names_and_skips_nameless_nodes(self, tmp_path):
        kg = {
            "nodes": [
                {"name": "A/B", "type": "concept", "descriptions": ["slashy"]},
                {"name": "", "type": "concept"},
            ],
            "relationships": [],
        }
        created = generate_all(kg, tmp_path, doc_types=["glossary"])
        briefs = {p.name for p in created if p.parent.name == "entities"}
        # Slash sanitised to dash; the nameless node produces no brief.
        assert briefs == {"A-B.md"}

    def test_creates_missing_output_dir(self, tmp_path):
        out = tmp_path / "nested" / "docs"
        created = generate_all(_sample_kg(), out, doc_types=["summary"])
        assert out.is_dir()
        assert (out / "summary.md").exists()
        assert len(created) == 6  # 1 doc + 5 briefs
