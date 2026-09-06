"""Panel progress, strict kerness outcomes, and independently attributed votes."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import kerness

PANELS = {
    "pr": (
        ("Style", "style_officer.md"),
        ("Naming", "naming_conventions.md"),
        ("Duplication", "duplication_hunter.md"),
        ("Quality", "code_quality.md"),
        ("Fit", "project_fit.md"),
        ("Dependencies", "dependency_auditor.md"),
        ("Security", "security_reviewer.md"),
    ),
    "issue": (("Reproducer", "issue_reproducer.md"), ("Scope", "issue_scoper.md")),
    "docs": (
        ("DocsPlanner", "docs_planner.md"),
        ("DocsWriter", "docs_writer.md"),
        ("DocsVerifier", "docs_verifier.md"),
    ),
}
PHASES = {
    "pr": ("study_repo", "review_pr", "cross_check", "verify", "vote"),
    "issue": ("study_repo", "investigate", "verify"),
    "docs": ("plan", "draft", "verify"),
}
TITLES = {
    "Style": "Language and tooling specialist",
    "Naming": "Public API designer",
    "Duplication": "Refactoring specialist",
    "Quality": "Senior software engineer",
    "Fit": "Software architect",
    "Dependencies": "Supply chain researcher",
    "Security": "Security researcher",
    "Reproducer": "Failure analysis engineer",
    "Scope": "Product and architecture triager",
    "Chair": "Maintainer and release chair",
    "DocsPlanner": "Architecture planner",
    "DocsWriter": "Architecture writer",
    "DocsVerifier": "Architecture verifier",
}


class PanelError(RuntimeError):
    """The panel did not produce a complete, attributable result."""


class PanelChannel(kerness.Channel):
    """Show progress on stderr; retain the full conversation only when requested.

    Deliver the transcript directly so a failed write stops the run. Kerness's
    MultiChannel intentionally swallows member errors, which would lose an
    explicitly requested audit trail.
    """

    def __init__(self, kind: str, transcript: Path | None = None, verbose: bool = False):
        self.kind = kind
        self.verbose = verbose
        self.transcript = kerness.FileChannel(str(transcript)) if transcript else None
        self.destination = transcript
        self.seats = [name for name, _ in PANELS[kind]]
        self.completed = 0

    def paths(self) -> list[Path]:
        return [self.destination] if self.destination else []

    def send(self, sender: str, message: str) -> None:
        if self.transcript:
            self.transcript.send(sender, message)
        if self.verbose:
            print(f"\n[{TITLES.get(sender, sender)} · {sender}]\n{message}", file=sys.stderr)
        elif sender in self.seats:
            index = min(self.completed // len(self.seats), len(PHASES[self.kind]) - 1)
            phase = PHASES[self.kind][index].replace("_", " ")
            print(
                f"  [{phase}] {TITLES[sender]} completed",
                file=sys.stderr,
                flush=True,
            )
        if sender in self.seats:
            self.completed += 1

    def send_system(self, message: str) -> None:
        if self.transcript:
            self.transcript.send_system(message)
        text = message if self.verbose else " ".join(message.split())[:180]
        print(f"  [panel] {text}", file=sys.stderr, flush=True)


@dataclass
class PanelResult:
    fields: dict
    history: list[dict]
    summary: str
    turns_completed: int
    rounds_run: int
    phase_reached: str
    end_reason: str
    votes: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)

    @property
    def final_summary(self) -> str:
        return self.summary


def _ballot(value: object, agent: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"vote", "reason"}:
        raise PanelError(f"{agent} must supply one ballot with exactly vote and reason.")
    if value["vote"] not in ("merge", "hold", "reject"):
        raise PanelError(f"{agent} supplied an invalid merge vote.")
    reason = value["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise PanelError(f"{agent}'s ballot has no reason.")
    return {"agent": agent, "vote": value["vote"], "reason": reason.strip()}


def _final_record(message: dict, prefix: str) -> object:
    agent = message["sender"]
    lines = message["content"].strip().splitlines()
    records = [line for line in lines if line.startswith(prefix + " ")]
    if len(records) != 1 or lines[-1] != records[0]:
        raise PanelError(f"{agent}'s final turn must end with exactly one {prefix} JSON line.")
    try:
        return json.loads(records[0][len(prefix) + 1:])
    except json.JSONDecodeError as exc:
        raise PanelError(f"{agent}'s {prefix} record is malformed JSON.") from exc


def validate_panel(result: PanelResult, kind: str) -> None:
    """Require actual participant turns in every phase before trusting a verdict.

    Kerness counts a round only when all registered participants have spoken.
    Phases move forward only, so the exact completed-round count plus the full
    authenticated rotation establishes phase participation without trusting a
    phase label that a model could put in its own prose.
    """
    seats = [name for name, _ in PANELS[kind]]
    phases = PHASES[kind]
    if (
        result.end_reason != "phases_complete"
        or result.phase_reached != phases[-1]
        or result.rounds_run != len(phases)
    ):
        raise PanelError(
            f"Incomplete {kind} panel: ended {result.end_reason!r} at "
            f"{result.phase_reached!r}, with {result.rounds_run}/{len(phases)} rounds."
        )
    turns = [message for message in result.history if message.get("msg_type") == "turn"]
    if [message.get("sender") for message in turns] != seats * len(phases):
        raise PanelError("The recorded participant turns do not cover every seat in every phase.")
    if any(not str(message.get("content") or "").strip() for message in turns):
        raise PanelError("A specialist supplied an empty turn; its check did not complete.")
    if kind == "docs":
        # Exact rotation above establishes this is DocsVerifier's verify turn.
        # A chair's audited=true cannot override the independent verifier.
        audit = _final_record(turns[-1], "DOCS_AUDIT")
        if (
            not isinstance(audit, dict)
            or set(audit) != {"accepted", "reason"}
            or audit["accepted"] is not True
            or not isinstance(audit["reason"], str)
            or not audit["reason"].strip()
            or result.fields.get("audited") is not True
        ):
            raise PanelError("DocsVerifier did not accept the final documentation proposal.")
    if kind != "pr":
        return
    votes = []
    for message in turns[-len(seats):]:
        agent = message["sender"]
        value = _final_record(message, "BALLOT")
        votes.append(_ballot(value, agent))
    # This field is the chair's own final answer. No chair field can substitute
    # for a specialist: those seven ballots came from attributed turns above.
    votes.append(_ballot(result.fields.get("chair_vote"), "Chair"))
    result.votes = votes


def run_session(session: kerness.Session, kind: str) -> PanelResult:
    """Use kerness's strict owned run API; never publish coerced default fields."""
    if kind not in PANELS:
        raise ValueError(f"Unknown panel kind: {kind}")
    run = session.start(mode="automatic", result_validation="strict")
    while True:
        step = run.step()
        if step["status"] == "progress":
            continue
        if step["status"] != "finished":
            raise PanelError("The read-only panel unexpectedly requested external input.")
        outcome = step["outcome"]
        if outcome["reason"]["kind"] != "completed" or not outcome["diagnostics"]["valid"]:
            reason = outcome["reason"]["kind"]
            detail = outcome.get("error") or outcome.get("diagnostics")
            raise PanelError(f"Panel ended with {reason}: {detail}")
        raw = outcome["result"]
        result = PanelResult(
            fields=raw["fields"], history=raw["history"], summary=raw["final_summary"],
            turns_completed=raw["turns_completed"], rounds_run=raw["rounds_run"],
            phase_reached=raw["phase_reached"], end_reason=raw["end_reason"],
            usage=outcome["usage"],
        )
        validate_panel(result, kind)
        return result
