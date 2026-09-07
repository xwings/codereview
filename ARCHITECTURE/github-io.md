---
eatmycode_version: "1.2.0"
---
# GitHub CLI access

## Goal

Use one audited GitHub CLI boundary for resource identification, reads and
permitted report writes (M1–M2).

## Status

`done` — resource detection, body-file posting and denied command checks pass.

## Code Structure

| File | Role |
| ---- | ---- |
| `github_io.py` | CLI boundary, authentication, fetches, detection and posts |
| `tests/test_workflow.py` | Mocked lookup/posting behavior and denied commands |

## Language and Conventions

Python follows the [root conventions](../ARCHITECTURE.md#coding-style-and-code-design).
`github_io.py:48` centralizes argv execution and `check=False` enables explicit
lookup fallback. Body writers (`github_io.py:109`) use UTF-8 temporary files
instead of command-line string construction. No local formatter/type-checker
configuration exists; tests patch the boundary without accessing GitHub.

## Design and Invariants

Service interactions remain in this owner. `_check_prefix` rejects known
GitHub merge, closure, raw-API and push forms, including recognized leading
options; it is a deny-list, not a complete command allowlist. Authentication checks the
installed CLI locally. `detect_kind` requires a successful lookup, so a failed
PR request alone cannot classify an issue (`github_io.py:93`). Reports use
body files with deterministic lifetime and no shell interpolation. Available
write helpers only submit PR reviews and issue comments; labels remain advice.

## Key Types and Entry Points

- `github_io.py:33` — `_check_prefix`: reject GitHub merges, closures, raw `gh api`,
  repository sync and Git pushes, including supported leading-option forms.
- `github_io.py:48` — `gh`: shared argv-based CLI runner with captured failures.
- `github_io.py:66` — `ensure_gh_ready`: require installed/authenticated CLI.
- `github_io.py:78` — `fetch_pr`: metadata including head revision/base/state.
- `github_io.py:87` — `fetch_issue`: description, labels and comments.
- `github_io.py:93` — `detect_kind`: a successful PR lookup wins; an issue
  requires its own successful lookup. Both failing never becomes issue triage.
- `github_io.py:109` — `post_pr_review`: temporary UTF-8 body file, explicit
  approve/comment action, no shell interpolation or body argument length limit.
- `github_io.py:117` — `post_issue_comment`: temporary body-file comment only.

## Interactions

[Workflow](review-cli.md) identifies the kind before source or documentation
preparation and checks PR metadata again before posting. [Git I/O](git-io.md)
fetches the PR ref through Git and performs an isolated local merge; it never
uses a GitHub merge operation. The [harness](harness.md) dependency researcher
can request read-only repository metadata through the same boundary. OSV/PyPI lookups use their own
HTTP endpoints and do not bypass GitHub write restrictions.

## How to Test

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile github_io.py
```

Expected: successful PR/issue lookups route correctly; failed lookups refuse;
dangerous command forms raise; posted text preserves literal Markdown and
newlines via a body file. Tests mock GitHub and never publish.

## Review and Refactor Guide

New service reads must reuse `gh`; changes to forbidden prefixes also affect
[Git](git-io.md). Detection changes belong in the existing successful/failed
lookup case; report-body changes belong in the literal-Markdown body-file case
in `tests/test_workflow.py`. Preserve the absence of GitHub merge/close/push/label
writes and consult [reporting](reporting.md) before changing approval actions.
Supporting a new host would also require CLI repository validation and profile
identity changes; it is not a local endpoint substitution.

## Open Gaps / Roadmap

- Wrappers are a code boundary, not an operating-system sandbox. Contributors
  must not add direct GitHub subprocess/API call sites outside this module.
- GitHub Enterprise is not supported.
- Detection needs up to two lookups; all failures are surfaced to the user.
