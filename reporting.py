"""Validate panel conclusions and render one concise, source-backed report."""

from __future__ import annotations

import copy
import re
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


PR_FIELDS = {"recommendation", "reason", "review_body", "findings", "checklist", "questions"}
ISSUE_FIELDS = {"classification", "response_body", "evidence", "next_steps", "labels", "questions"}


def exact_fields(data: object, expected: set[str]) -> None:
    if not isinstance(data, dict) or set(data) != expected:
        raise ReportError("result fields do not match the required contract")


def strings(data: dict, key: str) -> list[str]:
    items = data.get(key)
    if not isinstance(items, list) or any(not isinstance(s, str) or not s.strip() for s in items):
        raise ReportError(f"{key} must be a list of nonempty strings")
    return items


def validate_findings(findings: object, clone: Path) -> None:
    if not isinstance(findings, list):
        raise ReportError("findings must be a list")
    for finding in findings:
        if not isinstance(finding, dict) or not isinstance(finding.get("severity"), str) or finding["severity"] not in SEVERITIES:
            raise ReportError("finding has an invalid severity or shape")
        required = {"severity", "file", "line", "message", "fix"}
        if not required <= set(finding) <= required | {"fix_code"}:
            raise ReportError("finding has invalid fields")
        source_location(clone, finding)
        text_field(finding, "message")
        text_field(finding, "fix")
        if "fix_code" in finding and not isinstance(finding["fix_code"], str):
            raise ReportError("fix_code must be a string")


def validate_assessment(data: dict) -> None:
    if data.get("recommendation") not in ("merge", "hold", "reject"):
        raise ReportError("invalid merge recommendation")
    text_field(data, "reason")


def validate_pr_content(fields: dict, clone: Path) -> None:
    validate_assessment(fields)
    text_field(fields, "review_body")
    validate_findings(fields.get("findings"), clone)
    strings(fields, "questions")
    checklist = fields.get("checklist")
    if not isinstance(checklist, dict) or set(checklist) != set(CHECKS):
        raise ReportError("all seven checks must be reported exactly once")
    for check in checklist.values():
        exact_fields(check, {"status", "note"})
        if check["status"] not in ("pass", "concern", "blocker"):
            raise ReportError("invalid checklist status")
        text_field(check, "note")
    if not re.match(r"Need: (justified|unclear|unnecessary)\b", checklist["fit"]["note"]):
        raise ReportError("Fit must state its need conclusion and evidence")


def validate_issue_content(fields: dict, clone: Path) -> None:
    if fields.get("classification") not in ("bug", "feature", "documentation", "support", "upstream", "needs_information"):
        raise ReportError("invalid issue classification")
    text_field(fields, "response_body")
    evidence = fields.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ReportError("issue answer requires source or documentation evidence")
    for entry in evidence:
        exact_fields(entry, {"file", "line", "note"})
        source_location(clone, entry)
        text_field(entry, "note")
    for key in ("next_steps", "labels", "questions"):
        strings(fields, key)


def validate_stage(kind: str, actor: str, fields: dict, clone: Path) -> None:
    """Validate a participant's record before selecting the next reviewer."""
    if kind == "pr":
        if actor in {"Security", "Dependencies"}:
            exact_fields(fields, {"findings", "questions", "summary"})
            validate_findings(fields["findings"], clone)
            strings(fields, "questions")
            text_field(fields, "summary")
            return
        if actor not in {"Lead", "Verifier"}:
            raise ReportError("unknown PR reviewer")
        extra = "specialists" if actor == "Lead" else "finding_reviews"
        exact_fields(fields, PR_FIELDS | {extra})
        validate_pr_content(fields, clone)
        if actor == "Lead":
            specialists = fields["specialists"]
            if not isinstance(specialists, dict) or not set(specialists) <= {"Security", "Dependencies"}:
                raise ReportError("only Security and Dependencies consultation is supported")
            for name in specialists:
                text_field(specialists, name)
        else:
            reviews = fields["finding_reviews"]
            if not isinstance(reviews, list):
                raise ReportError("finding_reviews must be a list")
            for review in reviews:
                exact_fields(review, {"finding", "status", "reason", "file", "line"})
                if type(review["finding"]) is not int or review["finding"] < 1:
                    raise ReportError("invalid finding review number")
                if review["status"] not in ("confirmed", "withdrawn", "unresolved"):
                    raise ReportError("invalid finding review status")
                source_location(clone, review)
                text_field(review, "reason")
    elif kind == "issue":
        if actor not in {"Investigator", "Verifier"}:
            raise ReportError("unknown issue reviewer")
        exact_fields(fields, ISSUE_FIELDS | ({"verify"} if actor == "Investigator" else set()))
        validate_issue_content(fields, clone)
        if actor == "Investigator" and type(fields["verify"]) is not bool:
            raise ReportError("verify must be a boolean")
    else:
        raise ReportError("unknown review kind")


def assemble_pr(lead: dict, consultations: dict[str, dict], verified: dict,
                clone: Path) -> tuple[dict, list[dict]]:
    """Account for every candidate once; retain independent recommendations."""
    validate_stage("pr", "Lead", lead, clone)
    validate_stage("pr", "Verifier", verified, clone)
    names = [name for name in ("Security", "Dependencies") if name in lead["specialists"]]
    if list(consultations) != names:
        raise ReportError("requested consultations did not complete in order")
    candidates = list(lead["findings"])
    questions = list(lead["questions"])
    for name, consultation in consultations.items():
        validate_stage("pr", name, consultation, clone)
        candidates.extend(consultation["findings"])
        questions.extend(consultation["questions"])
    reviews = verified["finding_reviews"]
    if len(reviews) != len(candidates) or {r["finding"] for r in reviews} != set(range(1, len(candidates) + 1)):
        raise ReportError("Verifier must account for every proposed finding exactly once")
    dispositions = {r["finding"]: r for r in reviews}
    confirmed = []
    for number, finding in enumerate(candidates, 1):
        decision = dispositions[number]
        if decision["status"] == "confirmed":
            confirmed.append(finding)
        elif decision["status"] == "unresolved":
            questions.append(
                f"Unresolved {finding['severity']} finding at {finding['file']}:{finding['line']}: "
                f"{finding['message']} — {decision['reason']} "
                f"(verification: {decision['file']}:{decision['line']})."
            )
    confirmed.extend(verified["findings"])
    fields = copy.deepcopy({key: verified[key] for key in PR_FIELDS})
    fields["findings"] = copy.deepcopy(confirmed)
    fields["questions"] = list(dict.fromkeys([*questions, *verified["questions"]]))
    assessments = [{"agent": actor, "recommendation": record["recommendation"], "reason": record["reason"]}
                   for actor, record in (("Lead", lead), ("Verifier", verified))]
    return fields, assessments


def issue_needs_verification(classification: str, requested: bool) -> bool:
    return requested or classification not in {"support", "needs_information"}


def assemble_issue(initial: dict, verified: dict | None, clone: Path) -> dict:
    validate_stage("issue", "Investigator", initial, clone)
    required = issue_needs_verification(initial["classification"], initial["verify"])
    if required != (verified is not None):
        raise ReportError("issue verification does not match the investigation")
    if verified is not None:
        validate_stage("issue", "Verifier", verified, clone)
    final = initial if verified is None else verified
    fields = copy.deepcopy({key: final[key] for key in ISSUE_FIELDS})
    fields["questions"] = list(dict.fromkeys([*initial["questions"], *final["questions"]]))
    fields["verification"] = "single_investigation" if verified is None else "independent"
    return fields


def validate_pr(fields: dict, clone: Path, assessments: list[dict], pr: dict) -> tuple[str, list[str]]:
    """Independent agreement, completed checks, evidence and PR state gate approval."""
    exact_fields(fields, PR_FIELDS)
    validate_pr_content(fields, clone)
    if not isinstance(assessments, list) or len(assessments) != 2:
        raise ReportError("Lead and Verifier must each supply an assessment")
    for assessment, actor in zip(assessments, ("Lead", "Verifier")):
        exact_fields(assessment, {"agent", "recommendation", "reason"})
        if assessment["agent"] != actor:
            raise ReportError("Lead and Verifier must each supply an assessment")
        validate_assessment(assessment)
    if any(fields[key] != assessments[-1][key] for key in ("recommendation", "reason")):
        raise ReportError("final recommendation must match Verifier's assessment")
    reasons = []
    if any(f["severity"] in BLOCKING for f in fields["findings"]):
        reasons.append("Resolve all major and blocker findings.")
    if any(c["status"] != "pass" for c in fields["checklist"].values()):
        reasons.append("Resolve the outstanding review checks.")
    if not fields["checklist"]["fit"]["note"].startswith("Need: justified"):
        reasons.append("Establish a justified need for the change.")
    if fields["questions"]:
        reasons.append("Resolve the remaining questions and disagreements.")
    if any(a["recommendation"] != "merge" for a in assessments):
        reasons.append("Lead and Verifier do not both recommend merging.")
    if pr.get("isDraft") or pr.get("state") != "OPEN":
        reasons.append("Only an open, non-draft PR can be approved.")
    return ("comment", reasons) if reasons else ("approve", [])


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


def render_pr(fields: dict, clone: Path, assessments: list[dict], verdict: str,
              reasons: list[str], *, allow_approve: bool) -> str:
    findings = sorted(fields["findings"], key=lambda f: SEVERITIES[f["severity"]])
    if verdict == "approve":
        decision = "Ready to merge"
    elif any(f["severity"] in BLOCKING for f in findings):
        decision = "Changes requested"
    elif any(a["recommendation"] == "reject" for a in assessments):
        decision = "Do not merge"
    else:
        decision = "Hold"
    lines = [
        f"## PR verdict: {decision}", "", fields["review_body"].strip(), "",
    ]
    if reasons:
        lines += [f"- {reason}" for reason in reasons] + [""]
    if verdict == "approve" and not allow_approve:
        lines += ["GitHub action: comment. Approval requires `--allow-approve`.", ""]
    lines += ["### Review assessments", "", "| Reviewer | Recommendation | Reason |", "| --- | --- | --- |"]
    lines += [f"| {a['agent']} | {a['recommendation']} | {cell(a['reason'])} |" for a in assessments]
    lines += ["", "## Findings", ""]
    if findings:
        lines += [render_finding(i, f, clone) for i, f in enumerate(findings, 1)]
    else:
        lines += ["No confirmed code findings.", ""]
    if fields["questions"]:
        lines += ["### Remaining questions", ""] + [f"- {one_line(q)}" for q in fields["questions"]] + [""]
    lines += ["<details>", "<summary>Seven review checks</summary>", "",
              "| Check | Status | Evidence |", "| --- | --- | --- |"]
    for key, label in CHECKS.items():
        check = fields["checklist"][key]
        lines.append(f"| {label} | {check['status']} | {cell(check['note'])} |")
    lines += ["", "</details>", "", "Review scope: documentation and source inspection; target tests were not executed."]
    return "\n".join(lines)


def render_issue(fields: dict, clone: Path) -> str:
    exact_fields(fields, ISSUE_FIELDS | {"verification"})
    validate_issue_content(fields, clone)
    if fields["verification"] not in ("independent", "single_investigation"):
        raise ReportError("invalid issue verification status")
    if fields["verification"] == "single_investigation" and issue_needs_verification(fields["classification"], False):
        raise ReportError("this issue classification requires independent verification")
    lines = [f"## Issue assessment: {fields['classification']}", "", fields["response_body"].strip(), "",
             "### Evidence", ""]
    for entry in fields["evidence"]:
        lines.append(f"- `{entry['file']}:{entry['line']}` — {one_line(entry['note'])}")
    if fields["next_steps"]:
        lines += ["", "### Next steps", ""] + [f"- {one_line(step)}" for step in fields["next_steps"]]
    if fields["questions"]:
        lines += ["", "### Remaining questions", ""] + [f"- {one_line(q)}" for q in fields["questions"]]
    verification = ("Independent verification completed." if fields["verification"] == "independent"
                    else "Single investigation; independent verification was not requested.")
    lines += ["", verification,
              "", "Assessment based on documentation and source inspection; reproduction was not executed."]
    return "\n".join(lines)
