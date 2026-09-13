---
eatmycode_version: "2.0.0"
---
# Report validation and rendering

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `reporting.py`, result schemas, citations, candidate finding
accounting, issue verification, PR approval gates or final Markdown rendering.

## Responsibility and Status

Produce readable evidence-backed reports and enforce PR approval policy.
`done` — implemented; offline tests cover validation, rendering and independent
assessment gates. Citation existence cannot prove model interpretation.

## Code Map

| Path / symbol | Role |
| ------------- | ---- |
| `reporting.py:source_location` | Confined original-source citations |
| `reporting.py:validate_stage` | Exact role fields and nested evidence |
| `reporting.py:assemble_pr`, `assemble_issue` | Account for findings and preserve questions |
| `reporting.py:validate_pr` | Independent agreement and approval eligibility |
| `tests/test_workflow.py` | Report, issue, citation and verdict regressions |

## Local Conventions

The [root baseline](../../ARCHITECTURE.md#code-conventions) applies. Small pure
renderers return Markdown strings; validators raise `ReportError`. Reuse
`text_field` for nonempty text, `cell`/`fence` for safe Markdown, and dictionary
payloads. No local formatter/linter/type configuration exists.

## Contracts and Invariants

Citation paths resolve within the supplied source checkout and name readable
files; line positions must be real integers in range. Rendering reads original
source and never executes suggested fixes or performs GitHub writes.
Every role has exact fields. Findings require severity, source location,
problem and fix; optional `fix_code` is text. All seven product checklist keys
remain distinct, including `style` and `naming`. Fit notes begin with
`Need: justified`, `Need: unclear` or `Need: unnecessary`; missing context is a
concern, not fabricated evidence (`CHECKS`, `validate_pr_content`).

Every indexed candidate receives exactly one cited Verifier disposition.
Confirmed findings survive; withdrawn ones disappear; unresolved ones become
visible questions. Verifier's new findings survive too. Earlier questions are
unioned conservatively and both assessments remain visible. No tally or
rewritten final answer can erase disagreement (`assemble_pr`).

Approval requires Lead and Verifier both recommend merge, all seven checks
pass, justified need, no unanswered questions or major/blocker finding, and an
open non-draft PR. Final recommendation/reason must match Verifier's assessment.
`--allow-approve` independently controls delivery. A rendered hold cannot become
approval. An explicit rejection takes precedence over requested repairs.

PR Markdown opens with a verdict, exposes both assessments and all findings,
keeps checks expandable, and closes with the same verdict, explicit merge
instruction and approval reason/unmet requirements. Blocking findings include
bounded source excerpts and optional unexecuted fix sketches.

Issue answers require supported classification and source/doc evidence;
`issue_needs_verification` is the shared routing policy. Only `support` or
`needs_information` with `verify=false` may use one investigation. Other cases
or requested verification require Verifier. Host-set `verification` is
`independent` or `single_investigation`; rendering rejects inconsistent final
classification. Earlier questions remain visible. Reports disclose that target
tests/reproduction were not executed.

## Dependencies and Boundaries

[Panels](harness.md) authenticates attributed turns and rederives final fields;
read it for schema, routing or assessment changes. [Workflow](review-cli.md)
supplies selected/merged source and branch/base/revision scope, never generated
guide citations; read it for source/format changes. [GitHub](github-io.md) only
posts the validated action; consult it when approval delivery changes. PR
citations refer to local merge lines, which may differ from the PR head.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| -------------- | ---------------- | ---------------------- |
| Role schema/assessment | Stage validators and assembly; finding-accounting cases | Panels/gameplans and Workflow |
| Need/approval policy | `validate_pr`, `CHECKS`; need/state/assessment cases | Prompts and GitHub if action changes |
| Citations/rendering | `source_location`, renderers, escaping; report-ordering cases | Workflow scope, malformed citations and literal tables |
| Issue routing | Shared verification predicate and assembly/rendering | Panels and classification/evidence cases |

## Verification

Run [root checks](../../ARCHITECTURE.md#verification). `tests/test_workflow.py`
covers all seven checks, independent agreement, need/state gates, confirmations/
withdrawals/disputes, preserved questions, invalid citations, issue evidence,
table escaping and concise rendering. Report-ordering checks prove matching
opening/closing verdicts, merge instructions, reasons and rejection precedence.
Default CLI cases prove identical reports across verbosity without transcripts.
Passing means unittest `OK`, exit 0 and clean syntax; no target execution or
external writes occur.

## Known Gaps

Reports use one GitHub comment/review with no inline annotations. Large finding
sets can exceed service comment limits; pagination is not implemented or
accepted work. Independent review and maintainer judgment address semantic
interpretation beyond citation validity.
