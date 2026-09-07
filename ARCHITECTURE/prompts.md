---
eatmycode_version: "1.2.0"
---
# Repository profiles and shared prompts

## Goal

Supply optional project-specific review knowledge without confusing it with
the authoritative target source or current architecture guide (M1–M2).

## Status

`done` — profile precedence and generic fallback work without a shipped profile.

## Code Structure

| File | Role |
| ---- | ---- |
| `prompts/default/ARCHITECTURE.md` | Explains that no supplementary map is supplied |
| `prompts/default/design.md` | Generic severity and need/approval rubric |
| `prompts/coding_styles.md` | Shared style reference; the repository wins |
| `prompts/repos/README.md` | Optional owner/name profile conventions |
| `review.py` | Profile lookup and topic composition |

## Language and Conventions

Markdown profiles are read by Python. Follow the
[root conventions](../ARCHITECTURE.md#coding-style-and-code-design) for source,
and the observed need/severity vocabulary in `prompts/default/design.md`.
`review.py:168` supplies fallback text. No Markdown formatter or profile schema
checker is configured. Profiles carry supplementary prose only.

## Design and Invariants

Profiles are supplemental evidence, never target source authority or permission
to expand tools. An explicit profile wins over an owner/name directory, then
defaults apply. Required `--branch` selects the reviewed branch; profiles cannot
choose it. JSON branch pins and default-branch fallbacks were removed. Required
rubric/style files fail clearly when absent. Profile text cannot bypass the
host's approval or citation gates; repository-specific knowledge does not ship.

## Key Types and Entry Points

- `review.py:153` — `resolve_profile`: explicit `--prompts`, then
  `prompts/repos/<owner>/<name>`, then `prompts/default`.
- `review.py:168` — `_read_prompt`: profile → default → shared root; required
  design/style files missing is an error.
- `review.py:222` — `build_pr_topic`: prepared guide first, profile notes
  explicitly supplementary, then rubric/style/facts and the case.
- `review.py:274` — `build_issue_topic`: architecture and source-backed triage;
  it does not apply the PR approval rubric to an issue.
- `repo_facts.py:23` — `INDENT_LANGS`: measured languages match the shared style
  reference; other languages fall back to repository inspection.

The generic rubric retains the existing need assessment: concrete problem,
independent existing alternatives, placement and proportionality. Fit records
`Need: justified`, `Need: unclear` or `Need: unnecessary`; only justified need
can approve. Missing context is a concern, not an invented defect. A custom
rubric may strengthen policy, but cannot bypass host approval gates.

## Interactions

[Workflow](review-cli.md) resolves and announces a profile.
[Architecture preflight](architecture-preflight.md) supplies a prepared guide
and its audit status independently of that profile. [Harness personas](harness.md) own roles;
[reporting](reporting.md) enforces the final approval contract.

## How to Test

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile review.py
```

Expected: tests pass, including required explicit branch selection, and compile
exits zero. Source inspection establishes that no owner/name
profile ships and topic builders place prepared architecture before supplementary
notes (`review.py:222`, `review.py:274`); the suite does not assert that ordering.

## Review and Refactor Guide

For profile precedence changes inspect `resolve_profile` and `_read_prompt`
with [workflow](review-cli.md). Rubric wording changes
must preserve `Need:` conclusions accepted by [reporting](reporting.md) and
roles in [harness](harness.md). Run the workflow suite after profile changes.
Do not add a bundled project profile or move authoritative source facts into
a static prompt. Broader language guidance must agree with measured support
in `repo_facts.py`; unmeasured languages continue to rely on repository evidence.

## Open Gaps / Roadmap

- Profiles are manual supplementary snapshots and can become stale; source
  and prepared documentation take precedence.
- Only Python, C, C++ and Rust have measured style/symbol leads today.
