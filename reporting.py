"""Validate panel conclusions and render one concise, source-backed report."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

CHECKS = {
    "style": "Language conventions",
    "naming": "API naming",
    "duplication": "Reuse and duplication",
    "quality": "Code quality",
    "fit": "Need and architecture fit",
    "dependencies": "Dependencies and supply chain",
    "security": "Security",
}
BLOCKING = {"blocker", "major"}
SEVERITIES = {"blocker": 0, "major": 1, "nit": 2, "info": 3}


class ReportError(ValueError):
    """The panel did not provide sufficient evidence for a public report."""


def one_line(value: str) -> str:
    return " ".join(value.split())


def cell(value: str) -> str:
    return one_line(value).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def text_field(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReportError(f"missing or empty {key}")
    return value.strip()


def source_location(clone: Path, entry: dict) -> tuple[str, int, list[str]]:
    name = text_field(entry, "file")
    line = entry.get("line")
    root = clone.resolve()
    target = (root / name).resolve()
    if Path(name).is_absolute() or not target.is_relative_to(root) or not target.is_file():
        raise ReportError(f"citation is outside the checkout or missing: {name}")
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ReportError(f"cannot read cited source: {name}") from exc
    if type(line) is not int or not 1 <= line <= len(lines):
        raise ReportError(f"citation has no valid source line: {name}:{line}")
    return name, line, lines


def validate_pr(fields: dict, clone: Path, votes: list[dict], pr: dict) -> tuple[str, list[str]]:
    """Unanimity is necessary; evidence, rubric and PR state must also pass."""
    text_field(fields, "review_body")
    if fields.get("verdict") not in {"approve", "comment"}:
        raise ReportError("verdict must be approve or comment")
    findings = fields.get("findings")
    if not isinstance(findings, list):
        raise ReportError("findings must be a list")
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("severity") not in SEVERITIES:
            raise ReportError("finding has an invalid severity or shape")
        source_location(clone, finding)
        text_field(finding, "message")
        text_field(finding, "fix")
    checklist = fields.get("checklist")
    if not isinstance(checklist, dict) or set(checklist) != set(CHECKS):
        raise ReportError("all seven checks must be reported exactly once")
    for check in checklist.values():
        if not isinstance(check, dict) or check.get("status") not in {"pass", "concern", "blocker"}:
            raise ReportError("invalid checklist status")
        text_field(check, "note")
    need = checklist["fit"]["note"]
    if not re.match(r"Need: (justified|unclear|unnecessary)\b", need):
        raise ReportError("Fit must state its need conclusion and evidence")
    expected = {"Style", "Naming", "Duplication", "Quality", "Fit", "Dependencies", "Security", "Chair"}
    if len(votes) != len(expected) or {vote.get("agent") for vote in votes} != expected:
        raise ReportError("every specialist and the chair must cast a ballot")
    for vote in votes:
        if vote.get("vote") not in {"merge", "hold", "reject"}:
            raise ReportError("invalid merge ballot")
        text_field(vote, "reason")

    reasons = []
    if any(f["severity"] in BLOCKING for f in findings):
        reasons.append("Resolve all major and blocker findings.")
    if any(c["status"] != "pass" for c in checklist.values()):
        reasons.append("Resolve the outstanding review checks.")
    if not need.startswith("Need: justified"):
        reasons.append("Establish a justified need for the change.")
    if any(v["vote"] != "merge" for v in votes):
        reasons.append("The panel has not reached unanimous support for merging.")
    if fields["verdict"] != "approve":
        reasons.append("The chair recommends a comment under the review rubric.")
    if pr.get("isDraft") or pr.get("state") != "OPEN":
        reasons.append("Only an open, non-draft PR can be approved.")
    if not reasons:
        return "approve", []
    return "comment", reasons


def fence(body: str, language: str = "") -> str:
    width = max(3, 1 + max((len(s) for s in re.findall(r"`+", body)), default=0))
    ticks = "`" * width
    return f"{ticks}{language}\n{body}\n{ticks}"


def render_finding(number: int, finding: dict, clone: Path) -> str:
    name, line, source = source_location(clone, finding)
    lines = [
        f"### {number}. {finding['severity'].title()} — `{name}:{line}`", "",
        one_line(finding["message"]), "", f"**Fix:** {one_line(finding['fix'])}", "",
    ]
    if finding["severity"] in BLOCKING:
        excerpt = "\n".join(
            f"{'>' if n == line else ' '} {n} | {source[n - 1][:200]}"
            for n in range(max(1, line - 2), min(len(source), line + 2) + 1)
        )
        lines += ["<details>", "<summary>Source and suggested change</summary>", "", fence(excerpt), ""]
        sketch = finding.get("fix_code")
        if isinstance(sketch, str) and sketch.strip():
            lines += ["Suggested sketch (not executed):", "", fence("\n".join(sketch.splitlines()[:20])), ""]
        lines += ["</details>", ""]
    return "\n".join(lines)


def render_pr(fields: dict, clone: Path, votes: list[dict], verdict: str,
              reasons: list[str], *, allow_approve: bool) -> str:
    findings = sorted(fields["findings"], key=lambda f: SEVERITIES[f["severity"]])
    if verdict == "approve":
        decision = "Ready to merge"
    elif any(f["severity"] in BLOCKING for f in findings):
        decision = "Changes requested"
    elif any(v["vote"] == "reject" for v in votes):
        decision = "Do not merge"
    else:
        decision = "Hold"
    counts = Counter(v["vote"] for v in votes)
    lines = [
        f"## PR verdict: {decision}", "", fields["review_body"].strip(), "",
        f"**Vote:** {counts['merge']} merge · {counts['hold']} hold · {counts['reject']} reject.", "",
    ]
    if reasons:
        lines += [f"- {reason}" for reason in reasons] + [""]
    if verdict == "approve" and not allow_approve:
        lines += ["GitHub action: comment. Approval requires `--allow-approve`.", ""]
    lines += ["### Panel votes", "", "| Reviewer | Vote | Reason |", "| --- | --- | --- |"]
    lines += [f"| {v['agent']} | {v['vote']} | {cell(v['reason'])} |" for v in votes]
    lines += ["", "## Findings", ""]
    if findings:
        lines += [render_finding(i, f, clone) for i, f in enumerate(findings, 1)]
    else:
        lines += ["No confirmed code findings.", ""]
    lines += ["<details>", "<summary>Seven review checks</summary>", "",
              "| Check | Status | Evidence |", "| --- | --- | --- |"]
    for key, label in CHECKS.items():
        check = fields["checklist"][key]
        lines.append(f"| {label} | {check['status']} | {cell(check['note'])} |")
    lines += ["", "</details>", "", "Review scope: documentation and source inspection; target tests were not executed."]
    return "\n".join(lines)


def render_issue(fields: dict, clone: Path) -> str:
    classification = text_field(fields, "classification")
    if classification not in {"bug", "feature", "documentation", "support", "upstream", "needs_information"}:
        raise ReportError("invalid issue classification")
    answer = text_field(fields, "response_body")
    evidence = fields.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ReportError("issue answer requires source or documentation evidence")
    lines = [f"## Issue assessment: {one_line(classification)}", "", answer, "", "### Evidence", ""]
    for entry in evidence:
        if not isinstance(entry, dict):
            raise ReportError("invalid issue evidence")
        name, line, _ = source_location(clone, entry)
        note = text_field(entry, "note")
        lines.append(f"- `{name}:{line}` — {one_line(note)}")
    steps = fields.get("next_steps")
    labels = fields.get("labels")
    for key, items in (("next_steps", steps), ("labels", labels)):
        if not isinstance(items, list) or any(not isinstance(s, str) or not s.strip() for s in items):
            raise ReportError(f"{key} must be a list of nonempty strings")
    if steps:
        lines += ["", "### Next steps", ""] + [f"- {one_line(step)}" for step in steps]
    lines += ["", "Assessment based on documentation and source inspection; reproduction was not executed."]
    return "\n".join(lines)
