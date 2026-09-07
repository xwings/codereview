"""Assembles the kerness session: provider, agents, tool registry, access policy.

Gameplans declare tools and result contracts; panel_runtime owns review routing.
This module binds the checkout, endpoint and agents for one run.
"""

from __future__ import annotations

from pathlib import Path

import kerness

import agent_tools
from panel_runtime import PANELS, PanelChannel

ROOT = Path(__file__).resolve().parent
GAMEPLANS = ROOT / "gameplans"
PERSONAS = ROOT / "personas"

# Registered agents include optional PR consultants; the runtime selects them.
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
        documents = [docs_root / "ARCHITECTURE.md", *sorted((docs_root / "ARCHITECTURE").rglob("*.md"))]
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
    # Kerness otherwise supplies the gameplan body only to an orchestrator.
    # These reviews have no chair, so every participant needs the wire contract.
    instructions = None
    if kind != "docs":
        contract = kerness.load_gameplan(str(GAMEPLANS / gameplan)).body
        instructions = "You are {bot_name}. Follow your role's protocol below.\n\n" + contract

    session = kerness.Session(
        gameplan=str(GAMEPLANS / gameplan),
        topic=topic,
        provider=provider,
        channel=PanelChannel(kind, transcript, verbose, model),
        system_prompt=instructions,
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
    if kind == "docs":
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
