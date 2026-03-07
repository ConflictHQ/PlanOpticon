"""Skill: Generate a GitHub wiki from knowledge graph and artifacts."""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from video_processor.agent.skills.base import (
    AgentContext,
    Artifact,
    Skill,
    register_skill,
)

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Convert entity name to a wiki-safe filename."""
    return name.replace("/", "-").replace("\\", "-").replace(" ", "-").replace(".", "-")


def _wiki_link(name: str) -> str:
    """Create a GitHub wiki-style markdown link."""
    safe = _sanitize_filename(name)
    return f"[{name}]({safe})"


def generate_wiki(
    kg_data: dict,
    artifacts: Optional[List[Artifact]] = None,
    title: str = "Knowledge Base",
) -> Dict[str, str]:
    """Generate a dict of {filename: markdown_content} for a GitHub wiki.

    Returns pages for: Home, _Sidebar, entity type indexes, individual
    entity pages, and any planning artifacts.
    """
    pages: Dict[str, str] = {}
    artifacts = artifacts or []

    nodes = kg_data.get("nodes", [])
    relationships = kg_data.get("relationships", [])

    # Group entities by type
    by_type: Dict[str, list] = {}
    node_lookup: Dict[str, dict] = {}
    for node in nodes:
        name = node.get("name", node.get("id", ""))
        ntype = node.get("type", "concept")
        by_type.setdefault(ntype, []).append(node)
        node_lookup[name.lower()] = node

    # Build relationship index (outgoing and incoming per entity)
    outgoing: Dict[str, list] = {}
    incoming: Dict[str, list] = {}
    for rel in relationships:
        src = rel.get("source", "")
        tgt = rel.get("target", "")
        rtype = rel.get("type", "related_to")
        outgoing.setdefault(src, []).append((tgt, rtype))
        incoming.setdefault(tgt, []).append((src, rtype))

    # --- Home page ---
    home_parts = [
        f"# {title}",
        "",
        f"**{len(nodes)}** entities | **{len(relationships)}** relationships",
        "",
        "## Entity Types",
        "",
    ]
    for etype, elist in sorted(by_type.items()):
        home_parts.append(f"- {_wiki_link(etype.title())} ({len(elist)})")

    if artifacts:
        home_parts.append("")
        home_parts.append("## Planning Artifacts")
        home_parts.append("")
        for art in artifacts:
            safe = _sanitize_filename(art.name)
            home_parts.append(f"- [{art.name}]({safe})")

    pages["Home"] = "\n".join(home_parts)

    # --- Sidebar ---
    sidebar_parts = [f"**{title}**", "", "**Navigation**", "", "- [Home](Home)", ""]
    sidebar_parts.append("**Entity Types**")
    sidebar_parts.append("")
    for etype in sorted(by_type.keys()):
        sidebar_parts.append(f"- {_wiki_link(etype.title())}")

    if artifacts:
        sidebar_parts.append("")
        sidebar_parts.append("**Artifacts**")
        sidebar_parts.append("")
        for art in artifacts:
            safe = _sanitize_filename(art.name)
            sidebar_parts.append(f"- [{art.name}]({safe})")

    pages["_Sidebar"] = "\n".join(sidebar_parts)

    # --- Type index pages ---
    for etype, elist in sorted(by_type.items()):
        page_name = _sanitize_filename(etype.title())
        parts = [
            f"# {etype.title()}",
            "",
            f"{len(elist)} entities of type **{etype}**.",
            "",
            "| Entity | Descriptions |",
            "|--------|-------------|",
        ]
        for node in sorted(elist, key=lambda n: n.get("name", "")):
            name = node.get("name", "")
            descs = node.get("descriptions", [])
            desc_text = "; ".join(descs[:2]) if descs else "—"
            parts.append(f"| {_wiki_link(name)} | {desc_text} |")

        pages[page_name] = "\n".join(parts)

    # --- Individual entity pages ---
    for node in nodes:
        name = node.get("name", "")
        if not name:
            continue
        ntype = node.get("type", "concept")
        descs = node.get("descriptions", [])
        page_name = _sanitize_filename(name)

        parts = [
            f"# {name}",
            "",
            f"**Type:** {ntype}",
            "",
        ]

        if descs:
            parts.append("## Descriptions")
            parts.append("")
            for d in descs:
                parts.append(f"- {d}")
            parts.append("")

        # Outgoing relationships
        outs = outgoing.get(name, [])
        if outs:
            parts.append("## Relationships")
            parts.append("")
            parts.append("| Target | Type |")
            parts.append("|--------|------|")
            for tgt, rtype in outs:
                parts.append(f"| {_wiki_link(tgt)} | {rtype} |")
            parts.append("")

        # Incoming relationships
        ins = incoming.get(name, [])
        if ins:
            parts.append("## Referenced By")
            parts.append("")
            parts.append("| Source | Type |")
            parts.append("|--------|------|")
            for src, rtype in ins:
                parts.append(f"| {_wiki_link(src)} | {rtype} |")
            parts.append("")

        # Occurrences / sources
        occs = node.get("occurrences", [])
        if occs:
            parts.append("## Sources")
            parts.append("")
            for occ in occs:
                src = occ.get("source", "unknown")
                ts = occ.get("timestamp", "")
                text = occ.get("text", "")
                line = f"- **{src}**"
                if ts:
                    line += f" @ {ts}"
                if text:
                    line += f": _{text}_"
                parts.append(line)
            parts.append("")

        pages[page_name] = "\n".join(parts)

    # --- Artifact pages ---
    for art in artifacts:
        page_name = _sanitize_filename(art.name)
        if art.format == "json":
            try:
                data = json.loads(art.content)
                content = f"```json\n{json.dumps(data, indent=2)}\n```"
            except json.JSONDecodeError:
                content = art.content
        else:
            content = art.content

        pages[page_name] = f"# {art.name}\n\n{content}"

    return pages


def write_wiki(pages: Dict[str, str], output_dir: Path) -> List[Path]:
    """Write wiki pages to a directory as .md files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, content in pages.items():
        path = output_dir / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


def push_wiki(wiki_dir: Path, repo: str, message: str = "Update wiki") -> bool:
    """Push wiki pages to a GitHub wiki repo.

    Clones the wiki repo, copies pages, commits and pushes.
    The repo should be in 'owner/repo' format.
    """
    wiki_url = f"https://github.com/{repo}.wiki.git"

    # Clone existing wiki (or init if empty)
    clone_dir = wiki_dir / ".wiki_clone"
    if clone_dir.exists():
        subprocess.run(["rm", "-rf", str(clone_dir)], check=True)

    result = subprocess.run(
        ["git", "clone", wiki_url, str(clone_dir)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # Wiki might not exist yet — init a new repo
        clone_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=clone_dir, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", wiki_url],
            cwd=clone_dir,
            capture_output=True,
        )

    # Copy wiki pages into clone
    for md_file in wiki_dir.glob("*.md"):
        if md_file.parent == wiki_dir:
            dest = clone_dir / md_file.name
            dest.write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")

    # Commit and push
    subprocess.run(["git", "add", "-A"], cwd=clone_dir, capture_output=True)
    commit_result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=clone_dir,
        capture_output=True,
        text=True,
    )
    if commit_result.returncode != 0:
        logger.info("No wiki changes to commit")
        return True

    push_result = subprocess.run(
        ["git", "push", "origin", "master"],
        cwd=clone_dir,
        capture_output=True,
        text=True,
    )
    if push_result.returncode != 0:
        # Try main branch
        push_result = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=clone_dir,
            capture_output=True,
            text=True,
        )

    if push_result.returncode == 0:
        logger.info(f"Wiki pushed to {wiki_url}")
        return True
    else:
        logger.error(f"Wiki push failed: {push_result.stderr}")
        return False


class WikiGeneratorSkill(Skill):
    name = "wiki_generator"
    description = "Generate a GitHub wiki from knowledge graph and artifacts"

    def execute(self, context: AgentContext, **kwargs) -> Artifact:
        kg_data = context.knowledge_graph.to_dict()
        pages = generate_wiki(
            kg_data,
            artifacts=context.artifacts,
            title=kwargs.get("title", "Knowledge Base"),
        )

        # Return a summary artifact; actual pages are written via write_wiki()
        page_list = sorted(pages.keys())
        summary_parts = [
            f"Generated {len(pages)} wiki pages:",
            "",
        ]
        for name in page_list:
            summary_parts.append(f"- {name}.md")

        return Artifact(
            name="Wiki",
            content="\n".join(summary_parts),
            artifact_type="wiki",
            format="markdown",
            metadata={"pages": pages},
        )


register_skill(WikiGeneratorSkill())
