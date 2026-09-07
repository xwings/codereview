---
eatmycode_version: "1.2.0"
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
PR head into that branch. The architecture gate checks the root and recursive
Markdown set on this final source after eatmycode refresh (`review.py:423`, `review.py:310`). All versions
must match the fetched skill and every file must fit 35,000 Unicode characters
to skip the documentation panel. Missing, invalid, older or oversized files
require a local update; any newer version stops without downgrading. Findings
cite the selected or merged source, never generated guide lines; PR locations can differ from
GitHub PR-head lines. The final PR metadata comparison invalidates a changed head, base, state or draft flag.
`finish` owns stdout/posting; `--dry-run` uses the same architecture gate.
Measured regex facts are bounded leads, not review verdicts (`repo_facts.py:136`).

`progress.emit` formats stderr as `[YYYY-MM-DD HH:MM:SS] [model] [agent] [phase]`
using local wall time. `progress.activity` announces named steps before synchronous
work, prints a heartbeat every 15 seconds, and reports success with total duration.
Its yielded updater changes the current message, model, agent and phase together;
heartbeats retain that context and measure elapsed time with the monotonic clock. A scoped thread writes only
flushed stderr and is stopped and joined even on exceptions or interruption;
it does not execute work or impose timeouts. Status text is host-authored and identifies the configured model but excludes
credentials, endpoint URLs, request/response bodies and tool arguments. The panel
runtime shares this helper without importing the CLI. Stdout is flushed before
publication so a redirected report is available during the GitHub write.
`--verbose` and `--transcript` are optional; neither enables review execution.
Without them, the full review, format correction and final report still run.
Verbosity adds discussion text on stderr and does not change the report.

## Key Types and Entry Points

- `review.py:76` — `parse_args`: `--id NUMBER` for automatic PR/issue detection,
  required repository, branch and model credentials. Legacy `auto|pr|issue NUMBER`
  also works, but cannot be mixed with `--id`. Relative caller paths stay relative.
- `review.py:222` — `build_pr_topic`: prepared architecture, supplementary
  profile, rubric, style reference, measured facts, PR metadata and the pinned
  local merge diff.
- `review.py:274` — `build_issue_topic`: architecture, source context and issue.
- `review.py:310` — `prepare_docs`: check the final source's complete architecture
  version and size inventory; return that snapshot as the guide when current.
  Otherwise create a separate retained guide worktree and run preparation; never modify source.
- `review.py:359` — `handle_pr`: review the prepared local merge source and its
  guide, identify branch/base/review revisions in the topic and report, validate
  the result, then recheck PR head/state before publication.
- `review.py:402` — `handle_issue`: pinned selected-branch source and its guide,
  branch/revision scope, investigation with conditional verification, cited response and optional suggested
  labels on stderr.
- `review.py:423` — `main`: authenticate, detect kind, fetch applicable metadata,
  prepare selected-branch/local-merge source, refresh eatmycode, gate the final
  architecture set, then run the corresponding panel. Conflicts and changed fetched PR
  heads stop before documentation, model calls or posting.
- `repo_facts.py:136` — `collect`: deterministic leads for style, duplication and
  dependency reviewers; these regex-based measurements are not verdicts.
- `progress.py:22` — `activity`: context manager yielding a status updater;
  emits immediate/periodic stderr, joins its ticker on every exit and emits
  completion only on success. The launcher forwards this output directly.

## Interactions

[Architecture preflight](architecture-preflight.md) prepares the guide.
[Git](git-io.md) owns isolated source repositories, guide worktrees and revision
consistency; [GitHub](github-io.md) owns resource detection and publication. [Harness](harness.md) returns strict
results and authenticated assessments; [reporting](reporting.md) decides approval eligibility and renders it.
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
timestamped model/agent/phase output during blocked work, context updates and
cleanup on success, error and interruption.
Routing tests prove identification precedes source/docs work, issues use exactly
the selected branch, PRs use the local merge, and documentation is prepared once.
The scripted integration tests use the real kerness engine, without network
model calls or GitHub writes.
The default CLI integration case uses real argument parsing, architecture reuse,
session execution, report rendering and completion without a transcript; PR and
issue reports match with verbosity omitted or enabled, including format correction
and direct acceptance of complete indented, multiline, fenced or bare JSON results.

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

- Current architecture versions and sizes skip the documentation audit, so
  undetected content drift still requires source inspection by the review panel.
- `--timeout` is per request; there is no whole-run wall-clock budget.
- Independent source repositories and guide worktrees are retained for inspection
  and require cleanup.
- Python, C, C++ and Rust have measured style/symbol leads. Other languages
  rely on source inspection; no new language coverage is claimed.
- GitHub posting and live provider interpretation are not exercised by offline
  tests; scripted-session success does not prove either behavior.
