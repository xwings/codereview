---
eatmycode_version: "1.1.0"
---
# Workflow and launcher

## Goal

Coordinate selected-branch PR review and issue triage (M1–M3), while
keeping model orchestration, report policy and I/O in their owning modules.

## Status

`done` — offline workflow tests and launcher checks pass. Live model quality
and GitHub posting require configured credentials and are separate smoke checks.

## Code Structure

| File | Role |
| ---- | ---- |
| `review.py` | Arguments, profile resolution, topics and workflow coordination |
| `progress.py` | Shared activity messages, elapsed-time heartbeat and ticker cleanup |
| `code.sh` | Select the project virtual environment and forward arguments |
| `repo_facts.py` | Measured indentation, new symbols and manifest changes |
| `tests/test_workflow.py` | Workflow, real scripted panels, report and GitHub behavior |

## Language and Conventions

Python orchestration and a Bash launcher follow the [root conventions](../ARCHITECTURE.md#coding-style-and-code-design).
`parse_args` (`review.py:76`) is the canonical argparse boundary; topic builders
keep source authority separate from supplementary profile text. `code.sh:4`
quotes paths and forwards argv using `exec`; preserve caller-relative paths.
No module-specific formatter or type-checker configuration exists.

## Design and Invariants

`main` owns invocation order and case routing; lower layers own validation,
model execution and I/O. Required `--branch` selects the remote branch for
every case; profile pins and PR/default-branch fallbacks do not apply. Kind
detection and explicit mismatch rejection precede source preparation. Issues
use the pinned selected branch; PRs use an isolated local merge of the pinned
PR head into that branch. The root-version gate runs once on this final source
after eatmycode refresh (`review.py:419`, `review.py:310`). Only a missing or
outdated root runs the documentation panel. Findings cite the selected or
merged source, never generated guide lines; PR locations can differ from
GitHub PR-head lines. The final PR metadata comparison invalidates a changed head, base, state or draft flag.
`finish` owns stdout/posting; `--dry-run` uses the same root-version gate.
Measured regex facts are bounded leads, not review verdicts (`repo_facts.py:136`).

`progress.activity` announces named steps before synchronous work, prints an
elapsed-time heartbeat every 15 seconds, and reports success with total duration.
Its yielded updater identifies the current substep. A scoped thread writes only
flushed stderr and is stopped and joined even on exceptions or interruption;
it does not execute work or impose timeouts. Labels are host-authored and exclude
provider configuration, request/response bodies and tool arguments. The panel
runtime shares this helper without importing the CLI. Stdout is flushed before
publication so a redirected report is available during the GitHub write.

## Key Types and Entry Points

- `review.py:76` — `parse_args`: `--id NUMBER` for automatic PR/issue detection,
  required repository, branch and model credentials. Legacy `auto|pr|issue NUMBER`
  also works, but cannot be mixed with `--id`. Relative caller paths stay relative.
- `review.py:222` — `build_pr_topic`: prepared architecture, supplementary
  profile, rubric, style reference, measured facts, PR metadata and the pinned
  local merge diff.
- `review.py:274` — `build_issue_topic`: architecture, source context and issue.
- `review.py:310` — `prepare_docs`: check the final source's root version;
  return that snapshot as the guide immediately when current. Otherwise create
  a separate retained guide worktree and run preparation; never modify source.
- `review.py:356` — `handle_pr`: review the prepared local merge source and its
  guide, identify branch/base/review revisions in the topic and report, validate
  the result, then recheck PR head/state before publication.
- `review.py:399` — `handle_issue`: pinned selected-branch source and its guide,
  branch/revision scope, triage panel, cited response and optional suggested
  labels on stderr.
- `review.py:419` — `main`: authenticate, detect kind, fetch applicable metadata,
  prepare selected-branch/local-merge source, refresh eatmycode, gate the final
  root once, then run the corresponding panel. Conflicts and changed fetched PR
  heads stop before documentation, model calls or posting.
- `repo_facts.py:136` — `collect`: deterministic leads for style, duplication and
  dependency reviewers; these regex-based measurements are not verdicts.
- `progress.py:15` — `activity`: context manager yielding a status updater;
  emits immediate/periodic stderr, joins its ticker on every exit and emits
  completion only on success. The launcher forwards this output directly.

## Interactions

[Architecture preflight](architecture-preflight.md) prepares the guide.
[Git](git-io.md) owns isolated source repositories, guide worktrees and revision
consistency; [GitHub](github-io.md) owns resource detection and publication. [Harness](harness.md) returns strict
results; [reporting](reporting.md) decides approval eligibility and renders it.
[Profiles](prompts.md) supplement the source's facts.

## How to Test

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile review.py progress.py repo_facts.py
./code.sh --help
```

Expected: all tests pass, compile exits 0, help includes required `--branch`,
`--id`, `--verbose`, `--dry-run` and `--allow-approve`. Stdout from a review contains only Markdown;
progress and suggested labels go to stderr. The heartbeat lifecycle test proves
visible output during blocked work and cleanup on success, error and interruption.
Routing tests prove identification precedes source/docs work, issues use exactly
the selected branch, PRs use the local merge, and documentation is prepared once.
The scripted integration tests use the real kerness engine, without network
model calls or GitHub writes.

## Review and Refactor Guide

For argument or profile changes inspect `parse_args`, `main`
and [profiles](prompts.md), then extend the existing CLI/routing cases in
`tests/test_workflow.py`. Source/guide lifecycle changes also require
[Git](git-io.md), [preflight](architecture-preflight.md) and citation checks.
Reuse `documentation_context` to keep citation source separate from generated guides.
Keep provider internals and report eligibility out of orchestration. New
measurement support belongs in `repo_facts.py` with the shared style reference;
its success check is accurate measured leads without changing report policy.

## Open Gaps / Roadmap

- The final source checks the root version once. A missing/outdated root adds
  a model audit; a current root skips all documentation preparation.
- `--timeout` is per request; there is no whole-run wall-clock budget.
- Independent source repositories and guide worktrees are retained for inspection
  and require cleanup.
- Python, C, C++ and Rust have measured style/symbol leads. Other languages
  rely on source inspection; no new language coverage is claimed.
- GitHub posting and live provider interpretation are not exercised by offline
  tests; scripted-session success does not prove either behavior.
