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
| `prompts/default/profile.json` | Empty default: no pinned baseline branch |
| `prompts/coding_styles.md` | Shared style reference; the repository wins |
| `prompts/repos/README.md` | Optional owner/name profile conventions |
| `review.py` | Profile lookup and topic composition |

## Key Types and Entry Points

- `review.py:150` — `resolve_profile`: explicit `--prompts`, then
  `prompts/repos/<owner>/<name>`, then `prompts/default`.
- `review.py:165` — `profile_base_branch`: optional `base_branch` in JSON.
- `review.py:197` — `_read_prompt`: profile → default → shared root; required
  design/style files missing is an error.
- `review.py:251` — `build_pr_topic`: audited guide first, profile notes
  explicitly supplementary, then rubric/style/facts and the case.
- `review.py:303` — `build_issue_topic`: architecture and source-backed triage;
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
[Architecture preflight](architecture-preflight.md) supplies current source
facts independently of that profile. [Harness personas](harness.md) own roles;
[reporting](reporting.md) enforces the final approval contract.

## How to Test

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m json.tool prompts/default/profile.json
```

Expected: tests pass, default profile is `{}`, no owner/name profile ships,
and topic tests place audited architecture ahead of supplementary notes.

## Open Gaps / Roadmap

- Profiles are manual supplementary snapshots and can become stale; source
  and audited documentation take precedence.
- Only Python, C, C++ and Rust have measured style/symbol leads today.
