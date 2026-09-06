# Managed Git checkouts

## Goal

Provide clean, revision-consistent source snapshots and separate documentation
worktrees for PR and issue analysis (M1).

## Status

`done` — deny-list, revision and local worktree behavior passes checks.

## Code Structure

| File | Role |
| ---- | ---- |
| `git_io.py` | Git command boundary, clone and branch lifecycle, worktrees |
| `tests/test_workflow.py` | Dirty-clone, worktree and revision regressions |

## Key Types and Entry Points

- `git_io.py:12` — `git`: shared push deny-list, argv-based subprocess, captured
  output, clean error on nonzero exit.
- `git_io.py:30` — `ensure_clone`: create `<workdir>/<name>`, or verify the
  existing origin before reuse.
- `git_io.py:50` — `assert_clone_clean`: refuse to reset uncommitted work.
- `git_io.py:59` — `reset_to_branch`: fetch, checkout and reset the managed
  clean clone to the resolved baseline branch.
- `git_io.py:66` — `checkout_pr`: fresh `review/pr-N-SHA` branch through `gh`.
- `git_io.py:79` — `review_workspace`: retained unique detached worktree under
  `<workdir>/.reviews/`; source and generated guide worktrees are separate.
- `git_io.py:89` — `require_head`: fail if checkout raced the PR metadata.
- `git_io.py:95` — `pr_diff`: fetch the actual PR base and diff its merge base
  against local HEAD with external diff/text conversion disabled.

## Interactions

[Workflow](review-cli.md) resolves the baseline, enforces a clean managed clone,
creates source/guide snapshots and checks PR metadata again before publication.
[Architecture preflight](architecture-preflight.md) edits only the guide
worktree; [harness](harness.md) reads original source plus allowed guide files.
[GitHub I/O](github-io.md) supplies `gh pr checkout` and the shared deny-list.

## How to Test

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile git_io.py
```

Expected: all tests pass. Local temporary Git repositories exercise worktree
isolation without pushing, and dirty clones and changed heads are refused.

## Open Gaps / Roadmap

- Managed clones use repository name rather than owner/name. Same-name forks
  need separate workdirs; an origin mismatch is refused.
- Retained worktrees consume disk. Preserve desired generated docs before
  removing a worktree with Git; cleanup is not automatic.
- The workflow does not serialize simultaneous runs sharing a managed clone.
  Use separate `--workdir` paths for concurrent runs.
