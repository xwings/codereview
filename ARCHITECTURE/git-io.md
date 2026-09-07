---
eatmycode_version: "1.2.0"
---
# Managed Git checkouts

## Goal

Prepare the selected branch and optional local PR merge as an isolated source
repository, with separate documentation worktrees for PR and issue analysis (M1).

## Status

`done` — branch selection, local merge, configuration isolation and retained
source/guide behavior are covered by the offline workflow suite.

## Code Structure

| File | Role |
| ---- | ---- |
| `git_io.py` | Git command boundary, branch validation, isolated sources and guide worktrees |
| `tests/test_git_io.py` | Selected branches, local merges, races, conflicts and Git execution boundaries |
| `tests/test_workflow.py` | CLI routing and basic worktree/dirty-clone regressions |

## Language and Conventions

Python uses the [root conventions](../ARCHITECTURE.md#coding-style-and-code-design).
`git_io.py:24` is the canonical argv-based subprocess boundary; `Path` identifies
working directories, captured output is returned as `CompletedProcess`, and
checked command failure raises `SystemExit`. `Source` is a frozen dataclass.
Git 2.32+ is required for global/system configuration isolation through
`GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM`. There are no local formatter or
checker settings. Reuse temporary Git repositories from the workflow suite.

## Design and Invariants

This owner implements transport and filesystem snapshots, not review policy.
`prepare_source` validates the required branch and Git version, then refuses a
dirty managed clone (`git_io.py:83`). `ensure_clone` rejects an origin mismatch
before reuse (`git_io.py:62`). Fetches obtain objects and pin the selected branch
commit without checking out or resetting the managed working tree or local
branches. Per-run temporary refs pin both fetched revisions without reading or
writing shared `FETCH_HEAD`. Empty ref mappings prevent configured tracking or
local-branch updates. Temporary refs are removed after copying the source
objects, including on failure. A PR fetch must match its expected metadata head
before merging.

Each source is an independent retained Git repository under `<workdir>/.reviews/`,
with no object hardlinks or dependency on the managed clone's object lifetime.
Source preparation commands discard inherited Git environment overrides and ignore global
and system Git configuration. The new repository does not inherit managed-clone
configuration, custom merge drivers or filters. All Git calls disable hooks,
filesystem-monitor commands, automatic maintenance and recursive submodule work.
Managed clone creation first fetches without checkout, then discovers filters
in that repository, including conditional configuration, before materializing
its initial working tree with filters disabled. Cleanliness checks also disable
configured filters.
Initialized submodules are refused before reading their nested Git configuration;
uninitialized gitlinks are supported. No target hooks, scripts, filters, merge
drivers or submodule commands run.

An issue source is detached at the pinned selected branch. A PR source merges
its pinned head into that branch with no automatic commit. `commit-tree` records
the resulting tree in a synthetic local commit with the selected branch and PR
head as parents. The source ends detached at that revision; the diff compares
its pinned base directly with that result, with external diff and text
conversion disabled. Branch-only changes remain present without appearing as
incoming PR changes. A conflict stops before architecture preparation, model
calls or publication and retains the failed source for inspection.

Generated guides are retained detached worktrees attached to the isolated source
repository. Their edits remain uncommitted, separate from citation source. All
Git commands pass the shared push deny-list. Local merges never call a GitHub
merge endpoint or update the selected remote branch.

## Key Types and Entry Points

- `git_io.py:24` — `git`: shared push deny-list, argv execution, disabled hooks
  and maintenance, optional configuration/environment isolation and captured errors.
- `git_io.py:62` — `ensure_clone`: create `<workdir>/<name>`, or verify the
  existing origin before reuse, disabling checkout filters on creation.
- `git_io.py:83` — `assert_clone_clean`: refuse uncommitted work without running
  configured filters or modifying the managed working tree.
- `git_io.py:17` — `Source`: immutable source path, pinned base revision,
  reviewed revision and diff.
- `git_io.py:101` — `validate_branch`: require a branch name accepted under
  `refs/heads/`; reject empty names, option-like input and `HEAD` before fetching.
- `git_io.py:109` — `prepare_source`: fetch the selected branch and optional
  verified PR head; construct an independent source and optional local merge,
  returning `Source`.
- `git_io.py:167` — `review_workspace`: retained unique detached guide worktree
  under `<workdir>/.reviews/`, attached to the source repository.
- `git_io.py:177` — `require_head`: fail when a checkout has an unexpected revision.

## Interactions

[Workflow](review-cli.md) identifies the item, supplies the required branch and
optional PR metadata, then checks the final source's architecture once. It
rechecks PR metadata before publication. [Architecture preflight](architecture-preflight.md)
edits only a guide worktree; [harness](harness.md) reads the selected or merged
source plus allowed generated guide files. [GitHub I/O](github-io.md) supplies
metadata and the shared command deny-list; Git fetches PR refs itself.

## How to Test

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile git_io.py
```

Expected: all tests pass. Temporary repositories prove exact branch selection,
non-fast-forward local merges, both sides' preserved changes, pinned-base diffs,
unchanged managed working trees/local branches, disabled hooks and custom Git
execution, initialized-submodule rejection, conflict failures, dirty-clone
rejection and source/guide separation.
No test pushes or merges a PR on GitHub.

## Review and Refactor Guide

Branch or snapshot changes require reading `validate_branch`, `prepare_source`,
`review_workspace` and [CLI](review-cli.md) callers together. Preserve branch
validation, origin identity, clean-clone rejection, pinned revisions and source
isolation. Extend the existing local Git workflow cases. Inspect all commands
for inherited configuration, filters, hooks and custom merge drivers; a normal
Git checkout or merge can otherwise execute target code. Never replace explicit
pinned revisions with a later `FETCH_HEAD`. Keep subprocess execution in this
owner and generated documentation out of the reviewed source tree.

## Open Gaps / Roadmap

- Managed clones use repository name rather than owner/name. Same-name forks
  need separate workdirs; an origin mismatch is refused.
- Retained source repositories and guide worktrees have no automatic lifecycle
  cleanup; cleanup must preserve user-inspectable documentation artifacts.
- Per-run refs prevent another fetch from changing a selected revision. Clone
  creation, local object copying and the separate specification cache are not
  serialized; simultaneous runs can still fail and require retrying.
