---
eatmycode_version: "2.0.0"
---
# Workflow and launcher

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `review.py`, `code.sh`, `progress.py`, `repo_facts.py`, CLI
routing, selected source/guide coordination, output or progress lifecycle.

## Responsibility and Status

Coordinate PR review and issue triage while keeping model runtime, report
policy and I/O in their owners. `done` — implemented; offline workflow tests exercise
real scripted panels and the launcher. Live provider quality and posting are
outside that evidence.

## Code Map

| Path / symbol | Role |
| ------------- | ---- |
| `review.py:parse_args`, `main` | Invocation validation and ordered workflow |
| `review.py:prepare_docs` | Current-guide reuse or separate local preparation |
| `progress.py:activity` | Shared timestamped stderr and heartbeat cleanup |
| `repo_facts.py:collect`, `code.sh` | Bounded measured leads; venv selection/argv forwarding |
| `tests/test_workflow.py` | Routing, panels, reports, heartbeat, budgets and interruption |

## Local Conventions

[Root conventions](../../ARCHITECTURE.md#code-conventions) suffice. Argparse owns
CLI validation; lower layers raise errors and never import `review.py`.
`code.sh` uses strict Bash, quotes paths and directly `exec`s `.venv/bin/python`
or legacy `venv/bin/python`. Preserve caller-relative paths and exit status.

## Contracts and Invariants

`main` authenticates, identifies the item, rejects explicit kind mismatch,
fetches applicable PR metadata and prepares source before documentation/models.
`--id NUMBER` auto-detects; legacy `auto|pr|issue NUMBER` cannot be mixed with it.
Required `--repo` accepts supported github.com forms; required `--branch` selects
the exact remote branch. Profiles and GitHub defaults cannot choose it.
Credentials/model come from flags or `REVIEW_API_KEY`, `REVIEW_API_BASE`,
`REVIEW_MODEL`; positive number/timeouts/turn limits are validated.

Issues use the pinned selected branch; PRs use its isolated local merge with the
pinned head. Conflicts or changed fetched heads stop before docs/models/posting.
`prepare_docs` refreshes/gates the final source through the preflight owner,
reusing it as guide when current or creating a retained guide worktree for an
update. `--dry-run` follows the same source/docs/review path.

Review context provides the compact root and mandatory rules once, then routes
by source paths/task triggers to the relevant owner and matching topics. Use
matching index branches; load partner owners only when a changed boundary needs
them. Reuse unchanged context and inspect full relevant source. A separate
generated guide does not require rereading every original architecture page;
inspect original docs when a relevant claim or submitted documentation changes.
All findings cite selected/merged source, never generated guide lines. PR lines
can differ from GitHub PR-head lines (`documentation_context`, topic builders).

`finish` prints/flushes one Markdown report to stdout, then posts unless dry-run.
Progress and suggested labels use stderr. Before publication `handle_pr`
rechecks head, base name, state and draft flag; any change invalidates the
report. `--allow-approve` permits an approval only after report eligibility.
`--verbose` adds discussion; `--transcript` records an explicit file. Neither
enables execution or changes final report semantics.

`progress.emit` uses local `[YYYY-MM-DD HH:MM:SS] [model] [agent] [phase]`.
`activity` schedules flushed heartbeats every 15 seconds, measures activity and
scope with monotonic time, and updates context atomically. Its temporary thread
stops/joins on normal or exceptional exit; it imposes no timeout. Status text
excludes credentials, endpoint URLs, raw bodies and tool arguments. Read
[provider observation](../topics/provider-observation.md) when changing request
counts, retry labels, elapsed accounting or telemetry boundaries.

`--panel-timeout` defaults to a cooperative 3600-second budget for each panel;
`--api-timeout` is the per-attempt HTTP limit and also defaults to 3600 seconds.
Explicit flag values override these defaults. Active calls/retry waits can overrun
the budget; late results are rejected. `cli` temporarily uses OS-default SIGINT
so Ctrl+C terminates blocked native calls immediately. Imported library callers
retain their signal handling. OS termination bypasses Python cleanup; existing
artifacts, including partial transcripts, remain.

## Dependencies and Boundaries

Read [Git](git-io.md) for source/worktree lifecycle, [Preflight](architecture-preflight.md)
for guide freshness/context, [Panels](harness.md) for execution/limits, and
[Reports](reporting.md) for citation or result changes. Consult [GitHub](github-io.md)
for service detection/publication and [Prompts](prompts.md) for profile/topic
prose changes. These are conditional partner routes, not a startup reading list.
`repo_facts.collect` measures regex leads through Git; it cannot decide verdicts.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| -------------- | ---------------- | ---------------------- |
| CLI/options/profile selection | `parse_args`, `main`; CLI routing cases | Prompts if precedence changes; help and root suite |
| Source/guide context | `prepare_docs`, `documentation_context`, handlers | Git, Preflight, Panels and source citation cases |
| Progress/interruption/time | `activity`, `cli`; heartbeat/SIGINT/budget cases | Provider topic and Panels for request accounting |
| Measured language support | `repo_facts.py`, `prompts/coding_styles.md` | Prompts; precise leads without changing approval policy |

## Verification

Run [root checks](../../ARCHITECTURE.md#verification). The workflow suite proves
required branch/routing order, selected branch/local merge scope, one docs
preparation, and default CLI completion with no transcript. Scripted PR/issue
reports agree with verbosity off/on, including result-format correction and
multiline/fenced JSON. Heartbeat tests cover context updates and cleanup on
success/error/interruption. Local HTTP subprocess tests prove SIGINT during
native requests/retry waits; late-response tests prove elapsed-budget rejection.
Help must list `--branch`, `--id`, `--verbose`, `--dry-run`, `--api-timeout`,
`--panel-timeout` and `--allow-approve`. No external model call or GitHub write is exercised.

## Known Gaps

There is no whole-CLI deadline including Git/GitHub I/O. Source/guide artifacts
are retained without cleanup. Measured style/symbol leads cover Python, C, C++
and Rust; other languages need source inspection. Current guides may contain
semantic drift, so source inspection remains required. Broader measurements or
deadline work require explicit scope and behavioral checks; no new milestone
is accepted. Native retry sleeps may delay Python heartbeats.
