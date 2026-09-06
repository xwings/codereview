---
eatmycode_version: "1.1.0"
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
(`reporting.py:41`). PR approval requires eight merge votes, all seven passing
checks, justified need, approving rubric verdict, no major/blocker finding,
and an open non-draft PR (`reporting.py:57`). A hold remains distinguishable
from rejection. `--allow-approve` controls delivery separately from eligibility.
Issue answers require cited evidence but do not use the PR approval rubric.

## Key Types and Entry Points

- `reporting.py:22` — `ReportError` stops publication on unusable evidence.
- `reporting.py:41` — `source_location` resolves review-source citations,
  rejects escape/symlink escape and non-integer or out-of-range lines.
- `reporting.py:57` — `validate_pr` requires all checks, eight ballots and valid
  findings; approval additionally requires unanimity, justified need, passing
  checks, an approving rubric, zero major/blocker findings and an open non-draft PR.
- `reporting.py:107` — `fence` handles embedded backtick runs safely.
- `reporting.py:113` — `render_finding` gives each finding one location, problem
  and fix; blocking source excerpts and optional code sketches are expandable.
- `reporting.py:132` — `render_pr` leads with Ready to merge, Changes requested,
  Do not merge or Hold, followed by attributed votes, findings and checks.
- `reporting.py:168` — `render_issue` requires a supported classification and
  cited evidence, then renders the answer and actionable next steps.

## Interactions

[Workflow](review-cli.md) supplies the selected branch or local PR merge
source, never the rewritten documentation guide. It identifies the branch and
pinned base/review revisions in the result. PR citations may differ from lines
on the GitHub PR head. [Harness](harness.md) authenticates ballot
senders and checks completion before this module sees a result. The renderer
cannot promote a hold to approval, and `--allow-approve` controls the final
[GitHub action](github-io.md), independently from the panel's recommendation.

## How to Test

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile reporting.py
```

Expected: all cases pass, including eight-vote unanimity, need/checklist/state
gates, malformed citations, issue evidence, table escaping and concise output.
No target commands or external writes occur.

## Review and Refactor Guide

Schema changes must be coordinated with [gameplans and runtime](harness.md)
and [CLI](review-cli.md), then proved through the existing approval, citation,
report-ordering and issue-answer cases in `tests/test_workflow.py`. Reuse
`source_location` for all published evidence and escaping helpers for Markdown.
Keep ballot attribution in the runtime and posting in [GitHub](github-io.md).
Any future pagination must preserve a single unambiguous decision and all
findings; no pagination implementation is currently accepted.

## Open Gaps / Roadmap

- A valid citation proves that a source line exists, not that the model's
  interpretation is correct. Independent review and debate address semantics.
- Reports use one GitHub comment/review, without inline annotations.
- Large finding sets can exceed GitHub comment limits; no pagination is added.
