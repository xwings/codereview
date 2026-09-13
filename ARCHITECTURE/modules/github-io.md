---
eatmycode_version: "2.0.0"
---
# GitHub CLI access

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `github_io.py`, resource identification, service reads,
report writes, authentication or shared forbidden commands.

## Responsibility and Status

Own the audited GitHub CLI boundary for resource detection, reads and permitted
report writes. `done` — implemented; mocked offline cases verify routing, denial and
body-file behavior. Live GitHub posting is unverified by that suite.

## Code Map

| Path / symbol | Role |
| ------------- | ---- |
| `github_io.py:gh`, `_check_prefix` | Captured argv execution and known-command denial |
| `github_io.py:detect_kind` | Successful lookup-based PR/issue classification |
| `github_io.py:post_pr_review`, `post_issue_comment` | Temporary UTF-8 body-file writes |
| `tests/test_workflow.py` | Authentication/detection, unsafe forms and literal Markdown cases |

## Local Conventions

Use [root conventions](../../ARCHITECTURE.md#code-conventions). `check=False`
allows explicit lookup fallback; checked subprocess failure raises `SystemExit`.
Body writers use temporary files, with deterministic lifetime and no shell
interpolation. Tests mock the I/O boundary. No local checker is configured.

## Contracts and Invariants

Every GitHub service operation goes through `gh`. `_check_prefix` rejects known
merge/close/raw-API/repository-sync forms and Git pushes, including recognized
leading options. It is a deny-list, not a complete command allowlist.
Available write helpers only create PR reviews or issue comments; labels stay
advice. Never add GitHub merge, close, push or label writes.

`ensure_gh_ready` requires installed/authenticated `gh`. `detect_kind` first
tries PR lookup, then requires a successful issue lookup; it also recognizes
`/pull/` URLs returned by an issue endpoint. A failed PR request alone cannot
classify an issue. Both failures stop review. Fetch helpers return JSON metadata.

Posting preserves literal Markdown/newlines via `--body-file`, avoiding body
argument-length limits and shell expansion. PR approval versus comment is an
explicit argument supplied by validated caller policy, never inferred here.

## Dependencies and Boundaries

[Workflow](review-cli.md) identifies resources before preparing source and
rechecks PR metadata before publication; read it for detection/metadata changes.
[Git](git-io.md) fetches PR refs and makes isolated local merges; read it when
changing the shared deny-list. [Reporting](reporting.md) determines eligibility;
read it before changing approval actions. [Panels](harness.md) use this boundary
for upstream metadata; PyPI/OSV queries use their explicit separate endpoints.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| -------------- | ---------------- | ---------------------- |
| Detection or metadata | `detect_kind`, fetch helpers; successful/failed lookup case | Workflow ordering and race guards |
| Report text/action | Posting helpers; body-file regression | Reporting gates, Workflow delivery |
| Forbidden forms | `_check_prefix`; denied-command cases | Git owner and shared restrictions |

## Verification

Run [root checks](../../ARCHITECTURE.md#verification) from repository root with
the installed binding. `tests/test_workflow.py` verifies successful/failed
classification, denied forms, and exact Markdown/newlines through body files.
Expected evidence is unittest `OK`, exit 0 and clean syntax checks. These
tests mock GitHub and never publish.

## Known Gaps

The wrappers are a coding boundary, not an OS sandbox; do not add direct GitHub
subprocess/API call sites elsewhere. GitHub Enterprise is unsupported. Detection
can require two lookups and surfaces failures to the caller.
