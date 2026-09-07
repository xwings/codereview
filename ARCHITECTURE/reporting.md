---
eatmycode_version: "1.2.0"
---
# Report validation and rendering

## Goal

Produce readable source-backed reports and enforce PR approval policy (M2).

## Status

`done` — report, citation and approval behavior passes offline tests.

## Code Structure

| File | Role |
| ---- | ---- |
| `reporting.py` | Nested result validation, approval gate and Markdown rendering |
| `tests/test_workflow.py` | Positive reports and rejection/hold/error regressions |

## Language and Conventions

Python follows the [root conventions](../ARCHITECTURE.md#coding-style-and-code-design).
Small pure rendering helpers return Markdown strings; validation raises
`ReportError` (`reporting.py:22`). `text_field` is the canonical nonempty-text
check, and `cell`/`fence` own Markdown escaping. Payloads are dictionaries;
there is no local formatter, linter or type-checker configuration.

## Design and Invariants

The module reads cited review source and produces strings; it performs no
GitHub writes and never executes suggested fixes. Citation paths must resolve
inside the supplied checkout, and lines must be real integer positions
(`reporting.py:41`). PR approval requires Lead and Verifier both recommend
merging, all seven checks pass, need is justified, no unresolved question or
major/blocker remains, and the PR is open/non-draft. Style and naming are
separate checklist keys. `--allow-approve` controls delivery independently.
PR reports repeat the opening decision in a closing `Final verdict` section with
an explicit merge instruction and the approval reason or unmet gate requirements.
An explicit rejection takes precedence over requested fixes. A hold means do not
merge yet. Rendering does not change approval eligibility or GitHub delivery.

Stage schemas have exact fields. Each candidate finding receives one cited
Verifier disposition: confirmed findings survive, withdrawn ones are omitted,
and unresolved ones become visible questions. Verifier's new findings also
survive. Earlier questions are unioned conservatively; they cannot disappear
through a rewritten final answer. Both recommendations and reasons remain
visible, even when Verifier withdraws all findings. There is no vote tally.

Issue answers require source evidence, supported classification and concrete
next steps. `issue_needs_verification` owns the shared routing policy used by
live selection, authenticated replay, assembly and final rendering. The host sets `verification` to `independent` or
`single_investigation`; the latter permits only support/missing-information
answers. Verifier may correct the answer/classification but cannot silently
erase earlier unanswered questions. Source inspection never claims execution.

## Key Types and Entry Points

- `reporting.py:22` — `ReportError` stops publication on unusable evidence.
- `reporting.py:41` — `source_location` rejects citation escape,
  missing source and non-integer or out-of-range line positions.
- `reporting.py:127` — `validate_stage` checks role-specific exact
  schemas, all seven checks, questions and source evidence before the next turn.
- `reporting.py:170` — `assemble_pr` accounts for every candidate once
  and returns final fields plus independently attributed assessments.
- `reporting.py:212` — `assemble_issue` enforces required verification,
  selects the final answer and preserves questions from investigation.
- `reporting.py:226` — `validate_pr` checks final shape, assessments,
  evidence and approval eligibility; missing evidence can only produce a comment.
- `reporting.py:255` — `fence` handles embedded backtick runs safely.
- `reporting.py:261` — `render_finding` renders one location, problem
  and fix; blocking source excerpts and optional code sketches are expandable.
- `reporting.py:280` — `render_pr` leads with the verdict, then two
  assessments, confirmed findings, unresolved questions and seven checks;
  it closes with the same verdict, a merge instruction and reasons.
- `reporting.py:323` — `render_issue` validates/renders the answer,
  source evidence, next steps, questions and verification status.

## Interactions

[Workflow](review-cli.md) supplies the selected branch or local PR merge
source, never the rewritten documentation guide. It identifies the branch and
pinned base/review revisions in the result. PR citations may differ from lines
on the GitHub PR head. [Harness](harness.md) authenticates stage
senders and rederives final fields/assessments before this module sees a result. The renderer
cannot promote a hold to approval, and `--allow-approve` controls the final
[GitHub action](github-io.md), independently from the panel's recommendation.

## How to Test

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile reporting.py
```

Expected: all cases pass, including independent agreement, all seven checks,
need/state gates, candidate confirmations/withdrawals/disputes, preserved questions,
malformed citations, issue verification/evidence, table escaping and concise output.
The report-ordering case checks matching opening/closing verdicts, explicit merge
instructions, reasons and rejection precedence. The default CLI integration case
proves identical reports with or without `--verbose`, without a transcript.
No target commands or external writes occur.

## Review and Refactor Guide

Schema changes must be coordinated with [gameplans and runtime](harness.md)
and [CLI](review-cli.md), then proved through the existing approval, citation,
report-ordering and issue-answer cases in `tests/test_workflow.py`. Reuse
`source_location` for all published evidence and escaping helpers for Markdown.
Keep stage attribution in the runtime and posting in [GitHub](github-io.md).
Any future pagination must preserve a single unambiguous decision and all
findings; no pagination implementation is currently accepted.

## Open Gaps / Roadmap

- A valid citation proves that a source line exists, not that the model's
  interpretation is correct. Independent review addresses semantics.
- Reports use one GitHub comment/review, without inline annotations.
- Large finding sets can exceed GitHub comment limits; no pagination is added.
