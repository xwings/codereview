---
eatmycode_version: "2.0.0"
---
# Managed Git checkouts

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `git_io.py`, branch selection, local PR merges, managed clones,
source isolation, guide worktrees or Git execution boundaries.

## Responsibility and Status

Own Git transport and isolated selected-branch snapshots, optionally merged with
the pinned PR head. `done` — implemented; offline temporary-repository tests cover the
boundary. No remote merge, push or review policy belongs here. Artifacts remain
available after process exit.

## Code Map

| Path / symbol | Role |
| ------------- | ---- |
| `git_io.py:git` | Argv command boundary and configuration isolation |
| `git_io.py:ensure_clone`, `assert_clone_clean` | Origin and working-tree preservation |
| `git_io.py:prepare_source` | Pin branch/head and construct independent source |
| `git_io.py:review_workspace` | Retained detached documentation worktree |
| `tests/test_git_io.py`, Git cases in `tests/test_workflow.py` | Isolation, races, conflicts and dirty-clone evidence |

## Local Conventions

The [root conventions](../../ARCHITECTURE.md#code-conventions) suffice.
`Source` is a frozen dataclass, commands return captured `CompletedProcess`,
and checked failure raises `SystemExit`. Git 2.32+ is required for
`GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` isolation. No local checker config exists.

## Contracts and Invariants

`ensure_clone` creates `<workdir>/<repo-name>` or refuses an origin mismatch.
`prepare_source` validates the required branch and Git version, then refuses
dirty clones. Fetches update unique temporary refs, with empty ref mappings and
no shared `FETCH_HEAD` write; managed checkouts and local branches remain intact.
Temporary refs are removed even on failure. Fetched PR head must match metadata.

Each retained `<workdir>/.reviews/` source is an independent repository with no
object hardlinks or dependency on the clone's object lifetime. Its Git commands
discard inherited `GIT_*` overrides and global/system configuration. No managed
clone config, custom merge driver or filter is inherited. All Git calls disable
hooks, fsmonitor, automatic maintenance and recursive submodule work. Clone
creation fetches without checkout, discovers configured filters (including
conditional config), and disables them before materialization and cleanliness
checks. Initialized submodules are refused before reading their nested config;
uninitialized gitlinks remain supported. Target code never executes.

Issues detach at the pinned branch. PRs merge the pinned head without automatic
commit; `commit-tree` records a synthetic merge with both parents. Diffing uses
pinned base versus merged revision, disables external diff/text conversion and
retains branch-only changes without treating them as incoming PR changes.
Conflicts retain the failed source and stop before docs, models or publication.

Guides are retained detached worktrees attached to the isolated source. Their
edits remain uncommitted and separate from finding citations. Git calls share
the push deny-list; local merging never modifies a remote branch.

## Dependencies and Boundaries

[Workflow](review-cli.md) supplies branch/head metadata and consumes `Source`;
read it when changing source lifecycle. [GitHub](github-io.md) owns service
metadata and the shared deny-list; read it for command restrictions or head
validation. [Preflight](architecture-preflight.md) edits guides and
[panels](harness.md) grant their reads; consult those owners only when source/
guide separation changes. Neither owns Git transport.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| -------------- | ---------------- | ---------------------- |
| Branch/ref/merge behavior | `prepare_source`, `validate_branch`; source tests | This owner and Workflow; preserve pinning and clean clones |
| Worktree lifecycle | `review_workspace`; source/guide separation cases | Workflow, Preflight and Panels for changed boundaries |
| Command safety/config | `git`, filter helpers; execution-boundary cases | GitHub deny-list owner; no target program execution |

## Verification

From repository root with the installed binding, run
`.venv/bin/python -m unittest discover -s tests -p 'test_git_io.py' -v`.
Expect `OK` and exit 0. `GitSourceTests` proves exact branch selection,
non-fast-forward merges, pinned diffs, unchanged managed branches, disabled
custom programs, initialized-submodule refusal, races, conflicts and guide
separation. Run [root checks](../../ARCHITECTURE.md#verification) for integration
and syntax. No test pushes or merges on GitHub.

## Known Gaps

Same-name forks require distinct workdirs; origin mismatch is refused. Retained
sources/guides have no cleanup policy. Per-run refs protect pinning, but clone
creation and local object copying are not serialized across concurrent runs;
failures can require a retry. No broader concurrency work is accepted.
