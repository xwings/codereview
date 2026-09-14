"""Bounded reviews, strict kerness outcomes and authenticated agent results."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import kerness

import reporting
from progress import activity, emit
from provider_io import observe_requests

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
PANEL_TIMEOUT_MESSAGE = "panel time budget exhausted (--panel-timeout); review incomplete"


class PanelError(RuntimeError):
    """The panel did not produce a complete, attributable result."""


def _phase(kind: str, actor: str, completed: int) -> str:
    if kind != "docs":
        return "verify" if actor == "Verifier" else "review"
    phases = PHASES["docs"]
    index = completed // len(PANELS["docs"])
    return phases[index] if index < len(phases) else "summary"


class PanelChannel(kerness.Channel):
    """Deliver optional verbose exchanges and a requested transcript.

    Deliver the transcript directly so a failed write stops the run. Kerness's
    MultiChannel intentionally swallows member errors, which would lose an
    explicitly requested audit trail.
    """

    def __init__(self, kind: str, transcript: Path | None = None, verbose: bool = False, model: str = "-"):
        self.kind = kind
        self.verbose = verbose
        self.model = model
        self.completed = 0
        self.actor = "Host"
        self.transcript = kerness.FileChannel(str(transcript)) if transcript else None
        self.destination = transcript

    def paths(self) -> list[Path]:
        return [self.destination] if self.destination else []

    def send(self, sender: str, message: str) -> None:
        if self.transcript:
            self.transcript.send(sender, message)
        self.actor = sender
        if self.verbose:
            emit(message, model=self.model, agent=sender, phase=_phase(self.kind, sender, self.completed))
        if self.kind == "docs" and sender in {name for name, _ in PANELS["docs"]}:
            self.completed += 1

    def send_system(self, message: str) -> None:
        if self.transcript:
            self.transcript.send_system(message)
        if self.verbose:
            emit(message, model=self.model, phase=_phase(self.kind, self.actor, self.completed))


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


def _final_record(message: dict, prefix: str) -> object:
    agent = message.get("sender")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise PanelError(f"{agent} supplied an empty turn.")
    lines = content.strip().splitlines()
    if prefix == "RESULT":
        # Remove only a complete terminal JSON fence. Keep the original turn
        # untouched so execution and authenticated replay see the same evidence.
        if lines[-1].strip() == "```":
            fences = [i for i, line in enumerate(lines[:-1]) if line.strip().startswith("```")]
            if not fences or len(fences) % 2 != 1 or lines[fences[-1]].strip() not in {"```", "```json"}:
                raise PanelError(f"{agent}'s RESULT record has an unmatched JSON code fence.")
            opening = fences[-1]
            lines = lines[:opening] + lines[opening + 1:-1]
        records = [(i, re.match(r"^[ \t]*RESULT(?:[ \t]+|$)", line)) for i, line in enumerate(lines)]
        records = [(i, match) for i, match in records if match]
        if len(records) > 1:
            raise PanelError(f"{agent}'s final turn contains multiple RESULT records.")
        if records:
            index, match = records[0]
            if sum(line.strip().startswith("```") for line in lines[:index]) % 2:
                raise PanelError(f"{agent}'s RESULT record has an unmatched JSON code fence.")
            payload = "\n".join([lines[index][match.end():], *lines[index + 1:]]).strip()
        else:
            # A response consisting solely of JSON needs no marker; never mine
            # an object from arbitrary prose or choose between multiple objects.
            payload = "\n".join(lines).strip()
    else:
        records = [line for line in lines if line.startswith(prefix + " ")]
        if len(records) != 1 or lines[-1] != records[0]:
            raise PanelError(f"{agent}'s final turn must end with exactly one {prefix} JSON line.")
        payload = records[0][len(prefix) + 1:]
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise PanelError(f"{agent}'s {prefix} record is malformed JSON.") from exc


def _assemble_turns(turns: list[dict], kind: str, clone: Path) -> tuple[dict, list[dict]]:
    """Derive the route and result only from engine-attributed turns."""
    first = "Lead" if kind == "pr" else "Investigator"
    if not turns or turns[0].get("sender") != first:
        raise PanelError(f"The {kind} review must start with {first}.")
    stages = []
    attempts = iter(turns)
    for turn in attempts:
        actor = turn.get("sender")
        try:
            fields = _final_record(turn, "RESULT")
        except PanelError:
            corrected = next(attempts, None)
            if corrected is None or corrected.get("sender") != actor:
                raise PanelError(f"No same-agent format correction was recorded for {actor}.")
            fields = _final_record(corrected, "RESULT")
        stages.append((actor, fields))
    initial = stages[0][1]
    reporting.validate_stage(kind, first, initial, clone)
    if kind == "pr":
        consultants = [name for name in ("Security", "Dependencies") if name in initial["specialists"]]
        expected = ["Lead", *consultants, "Verifier"]
    else:
        verify = reporting.issue_needs_verification(initial["classification"], initial["verify"])
        expected = ["Investigator", *(["Verifier"] if verify else [])]
    if [actor for actor, _ in stages] != expected:
        raise PanelError("The recorded turns do not match the required review sequence.")
    remaining = dict(stages[1:])
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


def _failure(outcome: dict) -> str:
    """Describe engine failure without echoing provider URLs or response text."""
    reason = outcome["reason"]["kind"]
    if reason == "budget_exceeded" and outcome["reason"].get("budget") == "elapsed":
        return PANEL_TIMEOUT_MESSAGE
    error = outcome.get("error") or {}
    detail = next(iter(error), outcome["result"]["end_reason"])
    if detail == "ProviderHttp":
        detail += f" HTTP {error[detail]['status_code']}"
    elif detail == "ProviderNetwork" and "timed out" in error[detail]["cause"].lower():
        detail += ": request timed out"
    return f"{reason} ({detail})"


def _require_input(step: dict) -> None:
    if step["status"] == "finished":
        raise PanelError(f"The review stopped before the next required agent completed: "
                         f"{_failure(step['outcome'])}.")
    if step["status"] != "waiting" or step.get("reason", {}).get("kind") != "input":
        raise PanelError("The review stopped before the next required agent could complete.")


def _review_steps(run, kind: str, clone: Path, committed: list[dict], update) -> tuple[dict, list[dict]]:
    _require_input(_drain(run, run.step()))

    def select(actor: str, instruction: str) -> dict:
        for correction in (False, True):
            before = len(committed)
            step = run.step({"kind": "select_agent", "agent": actor, "instruction": instruction})
            _require_input(_drain(run, step))
            if len(committed) != before + 1 or committed[-1]["sender"] != actor:
                raise PanelError(f"No authenticated result was recorded for {actor}.")
            try:
                fields = _final_record(committed[-1], "RESULT")
                reporting.validate_stage(kind, actor, fields, clone)
                return fields
            except PanelError as exc:
                if correction:
                    raise PanelError(
                        f"{exc} Result-format correction failed: no complete review result was supplied. "
                        "The model must return the role's JSON result; --verbose only changes logging."
                    ) from exc
                update("requesting one result-format correction", agent=actor)
                instruction += (
                    f"\nYour previous response did not provide the required result record: {exc} "
                    "Correct only the result format, preserving your findings, evidence, questions "
                    "and conclusion. End with exactly one RESULT {JSON} line outside code fences, "
                    "using your role's exact fields from the gameplan. Use valid single-line JSON "
                    "with no text after it. This is your only format-correction attempt."
                )

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


def run_session(session: kerness.Session, kind: str, clone: Path | None = None,
                *, timeout_s: float = 900) -> PanelResult:
    """Run bounded PR/issue steps or the unchanged automatic documentation panel."""
    if kind not in PANELS:
        raise ValueError(f"Unknown panel kind: {kind}")
    if kind != "docs" and clone is None:
        raise PanelError("Review execution requires the source checkout.")
    label = {"pr": "PR review", "issue": "Issue investigation", "docs": "Documentation panel"}[kind]
    detail = "3 phases, 3 specialists" if kind == "docs" else "host-directed steps"
    models = {agent.name: agent.model for agent in session._agents}
    model = next(iter(models.values()), "-")
    seats = {name for name, _ in PANELS[kind]}
    completed = 0
    phase = _phase(kind, "Host", completed)
    committed = []
    started = time.monotonic()
    summarizer = "Chair" if kind == "docs" else PANELS[kind][0][0]
    with activity(f"{label} ({detail}; {timeout_s:g}s budget)", model=model, phase=phase) as update, \
            observe_requests(update, models, summarizer) as provider_progress:
        def on_event(record: dict) -> None:
            nonlocal completed, phase
            event = record["event"]
            # Only host-known identities and operation types reach progress.
            # Event payloads can contain source, tool arguments and model text.
            if event["kind"] == "provider_started":
                actor = event["actor"]
                if kind == "docs":
                    phase = ("summary" if event["purpose"] == "final summary" else
                             _phase(kind, actor, completed))
                else:
                    phase = _phase(kind, actor, completed)
                provider_progress.started(actor, phase)
            elif event["kind"] == "tool_started":
                actor = event["identity"]["actor"]
                update("inspecting evidence", model=models[actor], agent=actor, phase=phase)
            elif event["kind"] == "turn_committed":
                actor = event["actor"]
                if kind != "docs":
                    committed.append({"sender": actor, "content": event["text"], "msg_type": "turn"})
                if actor in seats:
                    completed += 1
                    update("review turn completed", model=models[actor], agent=actor, phase=phase)

        try:
            run = session.start(
                mode="automatic" if kind == "docs" else "host_driven",
                result_validation="strict", event_sink=on_event,
                budget={"max_elapsed_ms": int(timeout_s * 1000)},
            )
            assessments = []
            if kind == "docs":
                step = _drain(run, run.step())
            else:
                fields, assessments = _review_steps(run, kind, clone, committed, update)
                step = _drain(run, run.step({"kind": "finish", "result": fields}))
            if time.monotonic() - started >= timeout_s:
                raise PanelError(PANEL_TIMEOUT_MESSAGE)
            if step["status"] != "finished":
                raise PanelError("The read-only panel unexpectedly requested external input.")
            outcome = step["outcome"]
            if outcome["reason"]["kind"] != "completed" or not outcome["diagnostics"]["valid"]:
                raise PanelError(f"Panel ended with {_failure(outcome)}.")
        except (kerness.SessionError, PanelError) as exc:
            elapsed = time.monotonic() - started
            exhausted = elapsed >= timeout_s or PANEL_TIMEOUT_MESSAGE in str(exc)
            reason = (
                f"{PANEL_TIMEOUT_MESSAGE}. {elapsed:.1f}s elapsed; {timeout_s:g}s budget "
                "shared across agents, tools, HTTP attempts and retry waits."
                if exhausted else str(exc)
            )
            context = provider_progress.failure_context()
            hint = (
                " Increase --panel-timeout to allow more total review time; "
                "--api-timeout controls each HTTP attempt's limit."
                if exhausted else ""
            )
            raise PanelError(f"{label} could not complete: {reason} {context}{hint}".rstrip()) from exc
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
        update("validating participation and final result", model=model, agent="Host", phase="validate")
        validate_panel(result, kind, clone)
        return result
