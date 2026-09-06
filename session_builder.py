"""Assembles the kerness session: provider, agents, tool registry, access policy.

The harness itself is declared in `gameplans/`, not here. This module only
binds the declaration to this run — which checkout the agents may read, which
endpoint they talk to, and who sits on the panel.
"""

from __future__ import annotations

from pathlib import Path

import kerness

import agent_tools
from panel_runtime import PANELS, PanelChannel

ROOT = Path(__file__).resolve().parent
GAMEPLANS = ROOT / "gameplans"
PERSONAS = ROOT / "personas"

# Panel seat -> persona file. The order is the order of the seven checks, and
# the gameplan requires exactly this many participants.
PR_PANEL = PANELS["pr"]
ISSUE_PANEL = PANELS["issue"]
DOCS_PANEL = PANELS["docs"]
CHAIR = ("Chair", "maintainer_chair.md")


def build_provider(api_key: str, api_base: str, timeout_s: int) -> kerness.CustomProvider:
    """Any OpenAI-compatible endpoint. The key is held in memory only."""
    return kerness.CustomProvider(
        url=api_base,
        api_key=api_key,
        timeout_sec=timeout_s,
    )


def _build(
    kind: str,
    gameplan: str,
    panel: tuple[tuple[str, str], ...],
    tools: list[agent_tools.Tool],
    *,
    topic: str,
    clone: Path,
    provider: kerness.CustomProvider,
    model: str,
    transcript: Path | None,
    max_turns: int | None,
    verbose: bool = False,
    documentation: Path | None = None,
) -> kerness.Session:
    # Source is the workspace; only named guide files and a requested transcript
    # extend its boundary. Kerness rejects traversal and symlink escapes.
    # Commands remain unreachable because no gameplan declares a command tool.
    allowed_files = [str(transcript.resolve())] if transcript else []
    if documentation is not None:
        docs_root = documentation.resolve()
        documents = [docs_root / "ARCHITECTURE.md", *sorted((docs_root / "ARCHITECTURE").glob("*.md"))]
        for path in documents:
            resolved = path.resolve()
            if not resolved.is_relative_to(docs_root) or not resolved.is_file():
                raise ValueError(f"Documentation reference must be a file inside {docs_root}: {path}")
            allowed_files.append(str(resolved))
    policy = kerness.AccessPolicy(
        workspace=str(clone.resolve()),
        allowed_commands=["*"],
        # Outside the source checkout, grant only prepared architecture files
        # and an explicitly requested transcript, never the whole docs tree.
        allowed_files=allowed_files,
    )

    session = kerness.Session(
        gameplan=str(GAMEPLANS / gameplan),
        topic=topic,
        provider=provider,
        channel=PanelChannel(kind, transcript, verbose),
        access_policy=policy,
        max_turns=max_turns,
        turn_delay_sec=0,
        session_file=None,  # nothing about this run is written to disk
        # Inside the workspace, because the default `memory.md` resolves against
        # the launch directory and would fall outside it. Never created: the
        # session does not write memory.
        memory=str(clone.resolve() / "memory.md"),
    )

    for name, persona in panel:
        session.add_agent(name, model=model, persona=str(PERSONAS / persona))
    # `role` is what seats the chair; an agent that names none is a participant.
    session.add_agent(
        CHAIR[0], model=model, persona=str(PERSONAS / CHAIR[1]), role="orchestrator"
    )

    for tool_name, description, schema, handler in tools:
        session.add_tool(tool_name, description, schema, handler)

    return session


def build_pr_session(**kwargs) -> kerness.Session:
    clone = kwargs["clone"]
    return _build("pr", "pr_review.md", PR_PANEL, agent_tools.pr_tools(clone), **kwargs)


def build_issue_session(**kwargs) -> kerness.Session:
    clone = kwargs["clone"]
    return _build("issue", "issue_triage.md", ISSUE_PANEL, agent_tools.issue_tools(clone), **kwargs)


def build_docs_session(**kwargs) -> kerness.Session:
    clone = kwargs["clone"]
    return _build("docs", "architecture_docs.md", DOCS_PANEL, agent_tools.issue_tools(clone), **kwargs)
