"""Tests for wiki_generator gaps: entity Sources rendering, JSON artifacts,
the git push flow, and the skill execute() — none covered by test_agent_skills.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from video_processor.agent.skills.base import AgentContext, Artifact
from video_processor.agent.skills.wiki_generator import (
    WikiGeneratorSkill,
    generate_wiki,
    push_wiki,
)

_KG = {
    "nodes": [
        {
            "name": "Alice",
            "type": "person",
            "descriptions": ["An engineer"],
            "occurrences": [
                {"source": "transcript_0", "timestamp": 12.5, "text": "Alice spoke"},
                {"source": "notes"},
            ],
        },
        {"name": "Python", "type": "technology", "descriptions": ["A language"]},
        {"name": "", "type": "concept"},  # empty name -> skipped
    ],
    "relationships": [{"source": "Alice", "target": "Python", "type": "uses"}],
}


class TestGenerateWiki:
    def test_entity_page_renders_sources_and_relationships(self):
        pages = generate_wiki(_KG)
        alice = pages["Alice"]
        assert "## Sources" in alice
        assert "**transcript_0** @ 12.5: _Alice spoke_" in alice
        assert "**notes**" in alice  # occurrence with no timestamp/text
        assert "## Relationships" in alice
        assert "Python" in alice
        # Python is a relationship target -> "Referenced By" section
        assert "## Referenced By" in pages["Python"]

    def test_empty_name_node_produces_no_page(self):
        pages = generate_wiki(_KG)
        # only Home, _Sidebar, type indexes (Person/Technology), Alice, Python
        assert "" not in pages
        assert set(pages) >= {"Home", "_Sidebar", "Person", "Technology", "Alice", "Python"}

    def test_json_artifact_is_fenced_and_invalid_json_falls_back(self):
        good = Artifact(
            name="Task List",
            content=json.dumps([{"t": 1}]),
            artifact_type="task_list",
            format="json",
        )
        bad = Artifact(name="Broken", content="{not json", artifact_type="task_list", format="json")
        pages = generate_wiki(_KG, artifacts=[good, bad])
        assert "```json" in pages["Task-List"]
        # invalid JSON falls back to the raw content, unfenced
        assert pages["Broken"] == "# Broken\n\n{not json"
        # artifacts are linked from Home
        assert "Planning Artifacts" in pages["Home"]


def _fake_git(returncodes):
    """Build a subprocess.run stand-in keyed on the git subcommand/branch.

    On a successful clone it creates the clone dir (as real git would) so the
    subsequent page copy has somewhere to write.
    """

    def run(cmd, **kwargs):
        rc = 0
        if cmd[:2] == ["git", "clone"]:
            rc = returncodes.get("clone", 0)
            if rc == 0:
                Path(cmd[3]).mkdir(parents=True, exist_ok=True)
        elif len(cmd) >= 2 and cmd[1] == "commit":
            rc = returncodes.get("commit", 0)
        elif cmd[:3] == ["git", "push", "origin"]:
            rc = returncodes.get(f"push_{cmd[3]}", 0)
        return MagicMock(returncode=rc, stdout="", stderr="")

    return run


class TestPushWiki:
    def _wiki_dir(self, tmp_path):
        d = tmp_path / "wiki"
        d.mkdir()
        (d / "Home.md").write_text("# Home")
        return d

    def test_push_success_master(self, tmp_path):
        wiki = self._wiki_dir(tmp_path)
        (wiki / ".wiki_clone").mkdir()  # pre-existing clone dir -> exercises rm -rf
        with patch(
            "video_processor.agent.skills.wiki_generator.subprocess.run",
            side_effect=_fake_git({}),
        ) as mock_run:
            assert push_wiki(wiki, "org/repo") is True
        cmds = [c.args[0] for c in mock_run.call_args_list]
        assert ["git", "push", "origin", "master"] in cmds
        # the page was copied into the clone
        assert (wiki / ".wiki_clone" / "Home.md").read_text() == "# Home"

    def test_clone_failure_initializes_repo(self, tmp_path):
        wiki = self._wiki_dir(tmp_path)
        with patch(
            "video_processor.agent.skills.wiki_generator.subprocess.run",
            side_effect=_fake_git({"clone": 1}),
        ) as mock_run:
            assert push_wiki(wiki, "org/repo") is True
        cmds = [c.args[0] for c in mock_run.call_args_list]
        assert ["git", "init"] in cmds
        assert any(c[:3] == ["git", "remote", "add"] for c in cmds)

    def test_nothing_to_commit_returns_true(self, tmp_path):
        wiki = self._wiki_dir(tmp_path)
        with patch(
            "video_processor.agent.skills.wiki_generator.subprocess.run",
            side_effect=_fake_git({"commit": 1}),
        ) as mock_run:
            assert push_wiki(wiki, "org/repo") is True
        cmds = [c.args[0] for c in mock_run.call_args_list]
        # never reaches push when there is nothing to commit
        assert not any(c[:2] == ["git", "push"] for c in cmds)

    def test_falls_back_to_main_branch(self, tmp_path):
        wiki = self._wiki_dir(tmp_path)
        with patch(
            "video_processor.agent.skills.wiki_generator.subprocess.run",
            side_effect=_fake_git({"push_master": 1, "push_main": 0}),
        ) as mock_run:
            assert push_wiki(wiki, "org/repo") is True
        cmds = [c.args[0] for c in mock_run.call_args_list]
        assert ["git", "push", "origin", "main"] in cmds

    def test_push_failure_returns_false(self, tmp_path):
        wiki = self._wiki_dir(tmp_path)
        with patch(
            "video_processor.agent.skills.wiki_generator.subprocess.run",
            side_effect=_fake_git({"push_master": 1, "push_main": 1}),
        ):
            assert push_wiki(wiki, "org/repo") is False


class TestWikiGeneratorSkill:
    def test_execute_returns_summary_with_pages_metadata(self):
        ctx = AgentContext()
        ctx.knowledge_graph = MagicMock()
        ctx.knowledge_graph.to_dict.return_value = _KG
        ctx.artifacts = []
        result = WikiGeneratorSkill().execute(ctx, title="My KB")
        assert result.artifact_type == "wiki"
        assert "Generated" in result.content
        assert "Home.md" in result.content
        # actual page bodies are returned in metadata for write_wiki()
        assert "Home" in result.metadata["pages"]
        assert result.metadata["pages"]["Home"].startswith("# My KB")
