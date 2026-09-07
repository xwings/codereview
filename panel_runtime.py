"""Bounded reviews, strict kerness outcomes and authenticated agent results."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import kerness

import reporting
from progress import activity

PANELS = {
    "pr": (
        ("Lead", "lead_reviewer.md"),
        ("Security", "security_reviewer.md"),
        ("Dependencies", "dependency_auditor.md"),
        ("Verifier", "review_verifier.md"),
    ),
    "issue": (("Investigator", "issue_investigator.md"), ("Verifier", "issue_verifier.md")),
    "docs": (
        ("DocsPlanner", "docs_planner.md"),
        ("DocsWriter", "docs_writer.md"),
        ("DocsVerifier", "docs_verifier.md"),
    ),
}
PHASES = {"docs": ("plan", "draft", "verify")}
TITLES = {
    "Lead": "Lead reviewer",
    "Dependencies": "Supply chain researcher",
    "Security": "Security researcher",
    "Investigator": "Issue investigator",
    "Verifier": "Independent verifier",
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
            print(f"\n[{TITLES.get(sender, sender)} · {sender}]\n{message}", file=sys.stderr, flush=True)
        if sender in self.seats:
            self.completed += 1
            if self.kind == "docs":
                phases = PHASES["docs"]
                index = min((self.completed - 1) // len(self.seats), len(phases) - 1)
                total = len(self.seats) * len(phases)
                message = (
                    f"  [docs · phase {index + 1}/{len(phases)}: {phases[index]}] "
                    f"{TITLES[sender]} completed · specialist turns {self.completed}/{total}"
                )
            else:
                message = f"  [{self.kind} · step {self.completed}] {TITLES[sender]} completed"
            print(message, file=sys.stderr, flush=True)

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
    assessments: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)

    @property
    def final_summary(self) -> str:
        return self.summary


def _final_record(message: dict, prefix: str) -> object:
    agent = message.get("sender")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise PanelError(f"{agent} supplied an empty turn.")
    lines = content.strip().splitlines()
    records = [line for line in lines if line.startswith(prefix + " ")]
    if len(records) != 1 or lines[-1] != records[0]:
        raise PanelError(f"{agent}'s final turn must end with exactly one {prefix} JSON line.")
    try:
        return json.loads(records[0][len(prefix) + 1:])
    except json.JSONDecodeError as exc:
        raise PanelError(f"{agent}'s {prefix} record is malformed JSON.") from exc


def _stage(message: dict, kind: str, clone: Path) -> dict:
    fields = _final_record(message, "RESULT")
    reporting.validate_stage(kind, message["sender"], fields, clone)
    return fields


def _assemble_turns(turns: list[dict], kind: str, clone: Path) -> tuple[dict, list[dict]]:
    """Derive the route and result only from engine-attributed turns."""
    first = "Lead" if kind == "pr" else "Investigator"
    if not turns or turns[0].get("sender") != first:
        raise PanelError(f"The {kind} review must start with {first}.")
    initial = _stage(turns[0], kind, clone)
    if kind == "pr":
        consultants = [name for name in ("Security", "Dependencies") if name in initial["specialists"]]
        expected = ["Lead", *consultants, "Verifier"]
    else:
        verify = reporting.issue_needs_verification(initial["classification"], initial["verify"])
        expected = ["Investigator", *(["Verifier"] if verify else [])]
    if [turn.get("sender") for turn in turns] != expected:
        raise PanelError("The recorded turns do not match the required review sequence.")
    remaining = {turn["sender"]: _stage(turn, kind, clone) for turn in turns[1:]}
    if kind == "pr":
        consultations = {name: remaining[name] for name in consultants}
        return reporting.assemble_pr(initial, consultations, remaining["Verifier"], clone)
    return reporting.assemble_issue(initial, remaining.get("Verifier"), clone), []


def validate_panel(result: PanelResult, kind: str, clone: Path | None = None) -> None:
    """Authenticate required participation and rederive each published result."""
    turns = [message for message in result.history if message.get("msg_type") == "turn"]
    if kind != "docs":
        if clone is None:
            raise PanelError("Review validation requires the source checkout.")
        if result.end_reason != "host_finished" or result.turns_completed != len(turns):
            raise PanelError(f"Incomplete {kind} review: ended {result.end_reason!r}.")
        fields, assessments = _assemble_turns(turns, kind, clone)
        if result.fields != fields or result.assessments != assessments:
            raise PanelError("The final report does not match the authenticated agent results.")
        return

    seats = [name for name, _ in PANELS["docs"]]
    phases = PHASES["docs"]
    if (
        result.end_reason != "phases_complete"
        or result.phase_reached != phases[-1]
        or result.rounds_run != len(phases)
    ):
        raise PanelError(
            f"Incomplete docs panel: ended {result.end_reason!r} at "
            f"{result.phase_reached!r}, with {result.rounds_run}/{len(phases)} rounds."
        )
    if [message.get("sender") for message in turns] != seats * len(phases):
        raise PanelError("The recorded participant turns do not cover every seat in every phase.")
    if any(not str(message.get("content") or "").strip() for message in turns):
        raise PanelError("A specialist supplied an empty turn; its check did not complete.")
    # Exact rotation establishes DocsVerifier's verify turn; the chair cannot
    # override its independent rejection with an audited=true field.
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


def _drain(run, step: dict) -> dict:
    while step["status"] == "progress":
        step = run.step()
    return step


def _require_input(step: dict) -> None:
    if step["status"] != "waiting" or step.get("reason", {}).get("kind") != "input":
        raise PanelError("The review stopped before the next required agent could complete.")


def _review_steps(run, kind: str, clone: Path, committed: list[dict]) -> tuple[dict, list[dict]]:
    _require_input(_drain(run, run.step()))

    def select(actor: str, instruction: str) -> dict:
        before = len(committed)
        step = run.step({"kind": "select_agent", "agent": actor, "instruction": instruction})
        _require_input(_drain(run, step))
        if len(committed) != before + 1 or committed[-1]["sender"] != actor:
            raise PanelError(f"No authenticated result was recorded for {actor}.")
        return _stage(committed[-1], kind, clone)

    if kind == "pr":
        lead = select(
            "Lead",
            "Review the PR against the selected source and all seven checks. "
            "End with RESULT JSON as specified in the gameplan.",
        )
        catalogue = list(lead["findings"])
        for actor in ("Security", "Dependencies"):
            if actor in lead["specialists"]:
                consultation = select(
                    actor,
                    "Investigate this focused request from the lead using the original PR topic and source. "
                    "End with the consultant RESULT JSON. Request: " + lead["specialists"][actor],
                )
                catalogue.extend(consultation["findings"])
        indexed = [{"finding": index, **finding} for index, finding in enumerate(catalogue, 1)]
        select(
            "Verifier",
            "Independently inspect the source and all seven checks, including a clean review. "
            "Confirm, withdraw or leave unresolved EVERY indexed finding below with a source citation "
            "and reason. Put only NEW findings in your findings list. Review prior questions and preserve "
            "unresolved disagreements explicitly. End with the verifier RESULT JSON. Finding catalogue:\n"
            + json.dumps(indexed, ensure_ascii=False),
        )
    else:
        initial = select(
            "Investigator",
            "Investigate the issue on the selected source, explaining evidence and actionable next steps. "
            "Set verify=true for uncertain or substantial conclusions. End with investigator RESULT JSON.",
        )
        if reporting.issue_needs_verification(initial["classification"], initial["verify"]):
            select(
                "Verifier",
                "Independently read the relevant source to check the investigator's explanation and "
                "classification. Challenge unsupported claims, check the proposed next steps and "
                "give the final answer with source evidence. Do not merely restate the investigation. "
                "Keep unresolved questions visible; no further review turn will run. End with issue verifier RESULT JSON.",
            )
    return _assemble_turns(committed, kind, clone)


def run_session(session: kerness.Session, kind: str, clone: Path | None = None) -> PanelResult:
    """Run bounded PR/issue steps or the unchanged automatic documentation panel."""
    if kind not in PANELS:
        raise ValueError(f"Unknown panel kind: {kind}")
    if kind != "docs" and clone is None:
        raise PanelError("Review execution requires the source checkout.")
    label = {"pr": "PR review", "issue": "Issue investigation", "docs": "Documentation panel"}[kind]
    detail = "3 phases, 3 specialists" if kind == "docs" else "host-directed steps"
    committed = []
    with activity(f"{label} ({detail})") as update:
        def on_event(record: dict) -> None:
            event = record["event"]
            # Only host-known identities and operation types reach progress.
            # Event payloads can contain source, tool arguments and model text.
            if event["kind"] == "provider_started":
                actor = TITLES.get(event["actor"], "Panel agent")
                update(f"{label}: waiting for model response from {actor}")
            elif event["kind"] == "tool_started":
                actor = TITLES.get(event["identity"]["actor"], "Panel agent")
                update(f"{label}: {actor} inspecting evidence")
            elif event["kind"] == "turn_committed" and kind != "docs":
                committed.append({"sender": event["actor"], "content": event["text"], "msg_type": "turn"})

        try:
            run = session.start(
                mode="automatic" if kind == "docs" else "host_driven",
                result_validation="strict", event_sink=on_event,
            )
            assessments = []
            if kind == "docs":
                step = _drain(run, run.step())
            else:
                fields, assessments = _review_steps(run, kind, clone, committed)
                step = _drain(run, run.step({"kind": "finish", "result": fields}))
        except kerness.SessionError as exc:
            raise PanelError(f"{label} could not complete: {exc}") from exc
        if step["status"] != "finished":
            raise PanelError("The read-only panel unexpectedly requested external input.")
        outcome = step["outcome"]
        if outcome["reason"]["kind"] != "completed" or not outcome["diagnostics"]["valid"]:
            reason = outcome["reason"]["kind"]
            detail = outcome.get("error") or outcome.get("diagnostics")
            raise PanelError(f"Panel ended with {reason}: {detail}")
        raw = outcome["result"]
        if kind != "docs":
            recorded = [
                {key: message.get(key) for key in ("sender", "content", "msg_type")}
                for message in raw["history"] if message.get("msg_type") == "turn"
            ]
            if recorded != committed:
                raise PanelError("The final history differs from the authenticated turn events.")
        result = PanelResult(
            fields=raw["fields"], history=raw["history"], summary=raw["final_summary"],
            turns_completed=raw["turns_completed"], rounds_run=raw["rounds_run"],
            phase_reached=raw["phase_reached"], end_reason=raw["end_reason"],
            assessments=assessments, usage=outcome["usage"],
        )
        update(f"{label}: validating participation and final result")
        validate_panel(result, kind, clone)
        return result
