---
eatmycode_version: "2.0.0"
---
# codereview Architecture

## Read First

Before planning code changes or reviewing code, read
[Agent Rules](ARCHITECTURE/AGENT_RULES.md). Follow the Task Index to the
owning module and read pages whose **Read when** trigger matches the task.
Load partner modules only for affected boundaries; never load the entire
ARCHITECTURE directory. Reuse unchanged pages already read in this session.
Check claims against source, configuration, and tests; they remain
authoritative. If a route or fact is missing or stale, inspect source and
repair the affected docs. For broad changes, work through owners in batches
and retain cross-owner constraints and verification evidence.

## Project Snapshot

| Fact | Value and evidence |
| ---- | ------------------ |
| Purpose | Source-backed GitHub PR reviews and issue answers with independent verification; `review.py:main`. Every repo requires `--repo` and `--branch`; profiles only supplement source. |
| Support | Declared Linux/macOS, Python 3.10+, Git 2.32+, authenticated `gh`; [README](README.md). Bash launcher; Python modules/tests; Markdown/YAML gameplans and personas. |
| Dependency/build | Standard library plus pinned, patched kerness; [requirements](requirements.txt), [patch provenance](patches/README.md). Rust, C linker, Cargo/maturin build the binding through pip. |
| Non-goals | Never execute target tests/builds/scripts, merge on GitHub, push, close items or apply labels. This tool's offline development tests are separate. |

## System Design

`review.py:main` identifies the item, prepares an isolated selected-branch source
(locally merged PR head for PRs), refreshes eatmycode, prepares/reuses architecture
guidance, runs reviewers, validates and renders one report. Lower layers do not
import the CLI. `git_io.git` owns transport; `github_io.gh` owns GitHub access.
Only PR reviews and issue comments are available service writes.

Source is authoritative; generated guides never supply finding citations.
Reject dirty or wrong-origin managed clones and preserve their branches/work.
Panels have inspection tools only; reads stay within source, named guide files
and an optional caller-selected transcript (`session_builder._build`). Credentials
remain in memory and kerness persistence is disabled. Missing reviewers, invalid
citations/results, rejected docs audits or unavailable upstream rules stop
publication (`panel_runtime.validate_panel`, `architecture.sync_skill`).

## Code Conventions

Observed Python: four spaces, `snake_case`, `UPPER_CASE` constants, standard
library before local imports, postponed annotations and typed boundaries;
`Path`, fixed-record dataclasses and dictionary payloads (`session_builder.py`,
`reporting.py`). Typing is mixed; no formatter/linter/type checker or CI is
configured. Validation raises domain errors; CLI reports nonzero exits. Progress
uses flushed stderr; stdout is the final Markdown. Commands stay argv-based in
I/O owners. Tests use `unittest`, temporary repositories and scripted providers.

Required project additions: a second top-level dependency needs evidence that
the standard library cannot reasonably provide the behavior. Never treat ignored
`repo/` targets or `vendor/` caches as tool source. For binding/patch changes read
[kerness integration](ARCHITECTURE/topics/kerness-integration.md).

Project-specific deviations: shared rules govern this tool; target reviews
inspect source without target-test or release compliance claims. Product reports keep seven separate checklist keys (Style and
Naming separately), and Fit must record `Need: justified`, `Need: unclear` or
`Need: unnecessary` (`reporting.CHECKS`, `reporting.validate_pr_content`).

## Verification

Run from the repository root; setup uses the public pin and patch in
[README](README.md#setup), never a local-only dependency.

| Change/check | Command and working directory | Prerequisites / pass evidence |
| ------------ | ----------------------------- | ----------------------------- |
| Offline behavior | `.venv/bin/python -m unittest discover -s tests -v` | Installed binding; `OK`, exit 0. |
| Syntax/launcher | `.venv/bin/python -m compileall -q *.py tests`; `bash -n code.sh`; `./code.sh --help` | No diagnostics; documented options, exit 0. |
| Binding | `.venv/bin/python -m kerness.selfcheck` | `OK: all core checks passed`. |

Owner pages map specific checks. No separate app build/lint/type/CI target exists.
Offline tests use no external models or GitHub writes; live interpretation and
posting remain unverified. Architecture changes require current contract,
source, routing, links, size and stamp checks; see preflight owner.

## Task Index

| Source paths / task trigger | Responsibility | Read next |
| --------------------------- | -------------- | --------- |
| `review.py`, `code.sh`, `progress.py`, `repo_facts.py`; CLI/progress cases in `tests/test_workflow.py` | Coordination (profile exception below) | [Workflow](ARCHITECTURE/modules/review-cli.md) |
| `architecture.py`, `gameplans/architecture_docs.md`, `personas/docs_*.md`, `tests/test_architecture.py`, architecture docs; freshness/migration | Guide preparation | [Preflight](ARCHITECTURE/modules/architecture-preflight.md) |
| `panel_runtime.py`, `session_builder.py`, `provider_io.py`, `agent_tools.py`, remaining `gameplans/` and `personas/`, `patches/`, `requirements.txt`; panel tests | Review execution and tools | [Panels](ARCHITECTURE/modules/harness.md) |
| `reporting.py`; schema, citations, verdict/rendering tests | Report policy | [Reports](ARCHITECTURE/modules/reporting.md) |
| `github_io.py`; service/detection/body-file tests | GitHub boundary | [GitHub](ARCHITECTURE/modules/github-io.md) |
| `git_io.py`, `tests/test_git_io.py`; checkout/worktree tests | Git snapshots | [Git](ARCHITECTURE/modules/git-io.md) |
| `prompts/`, profile lookup and topic prose in `review.py` | Supplementary knowledge | [Prompts](ARCHITECTURE/modules/prompts.md) |
