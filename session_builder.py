"""Assembles the kerness session: provider, agents, tool registry, access policy.

The harness itself is declared in `gameplans/`, not here. This module only
binds the declaration to this run — which checkout the agents may read, which
endpoint they talk to, and who sits on the panel.
"""

from __future__ import annotations

from pathlib import Path

import kerness

import agent_tools

ROOT = Path(__file__).resolve().parent
GAMEPLANS = ROOT / "gameplans"
PERSONAS = ROOT / "personas"

# Panel seat -> persona file. The order is the order of the seven checks, and
# the gameplan requires exactly this many participants.
PR_PANEL = (
    ("Style", "style_officer.md"),
    ("Naming", "naming_conventions.md"),
    ("Duplication", "duplication_hunter.md"),
    ("Quality", "code_quality.md"),
    ("Fit", "project_fit.md"),
    ("Dependencies", "dependency_auditor.md"),
    ("Security", "security_reviewer.md"),
)
ISSUE_PANEL = (
    ("Reproducer", "issue_reproducer.md"),
    ("Scope", "issue_scoper.md"),
)
CHAIR = ("Chair", "maintainer_chair.md")


def build_provider(api_key: str, api_base: str, timeout_s: int) -> kerness.CustomProvider:
    """Any OpenAI-compatible endpoint. The key is held in memory only."""
    return kerness.CustomProvider(
        url=api_base,
        api_key=api_key,
        timeout_sec=timeout_s,
    )


def _channel(transcript: Path | None) -> kerness.Channel:
    console = kerness.ConsoleChannel()
    if transcript is None:
        return console
    return kerness.MultiChannel(console, kerness.FileChannel(str(transcript)))


def _build(
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
) -> kerness.Session:
    # The checkout is the world. A workspace grants everything under it and
    # nothing outside it, so this is both the read boundary — kerness resolves
    # paths and rejects `..` traversal and symlink escape itself — and the
    # directory a command would start in. `["*"]` is the anchored glob that
    # matches every command line; commands stay unreachable regardless, because
    # no gameplan declares the `cmd` tool.
    policy = kerness.AccessPolicy(
        workspace=str(clone.resolve()),
        allowed_commands=["*"],
        # The one path the run may touch outside the checkout, and only when
        # the maintainer named it. Session construction checks a channel's
        # destination against the same boundary as a model's read.
        allowed_files=[str(transcript.resolve())] if transcript else [],
    )

    session = kerness.Session(
        gameplan=str(GAMEPLANS / gameplan),
        topic=topic,
        provider=provider,
        channel=_channel(transcript),
        access_policy=policy,
        max_turns=max_turns,
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
    return _build("pr_review.md", PR_PANEL, agent_tools.pr_tools(clone), **kwargs)


def build_issue_session(**kwargs) -> kerness.Session:
    clone = kwargs["clone"]
    return _build("issue_triage.md", ISSUE_PANEL, agent_tools.issue_tools(clone), **kwargs)
