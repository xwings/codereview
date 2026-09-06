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

## Key Types and Entry Points

- `github_io.py:33` — `_check_prefix`: reject merges, closures, raw `gh api`,
  repository sync and Git pushes, including supported leading-option forms.
- `github_io.py:48` — `gh`: shared argv-based CLI runner with captured failures.
- `github_io.py:66` — `ensure_gh_ready`: require installed/authenticated CLI.
- `github_io.py:78` — `fetch_default_branch`: lazy baseline fallback.
- `github_io.py:91` — `fetch_pr`: metadata including head revision/base/state.
- `github_io.py:100` — `fetch_issue`: description, labels and comments.
- `github_io.py:106` — `detect_kind`: a successful PR lookup wins; an issue
  requires its own successful lookup. Both failing never becomes issue triage.
- `github_io.py:122` — `post_pr_review`: temporary UTF-8 body file, explicit
  approve/comment action, no shell interpolation or body argument length limit.
- `github_io.py:130` — `post_issue_comment`: temporary body-file comment only.

## Interactions

[Workflow](review-cli.md) identifies the kind after documentation preflight and
checks PR metadata again before posting. [Git I/O](git-io.md) uses `gh` for PR
checkout. The [harness](harness.md) dependency researcher can request read-only
repository metadata through the same boundary. OSV/PyPI lookups use their own
HTTP endpoints and do not bypass GitHub write restrictions.

## How to Test

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile github_io.py
```

Expected: successful PR/issue lookups route correctly; failed lookups refuse;
dangerous command forms raise; posted text preserves literal Markdown and
newlines via a body file. Tests mock GitHub and never publish.

## Open Gaps / Roadmap

- Wrappers are a code boundary, not an operating-system sandbox. Contributors
  must not add direct GitHub subprocess/API call sites outside this module.
- GitHub Enterprise is not supported.
- Detection needs up to two lookups; all failures are surfaced to the user.
