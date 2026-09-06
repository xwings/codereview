# Architecture preflight

## Goal

Establish a current, source-backed architecture map before routing a GitHub
item to PR review or issue triage. This is infrastructure for the review
workflow: both panels receive the root control center, owning module paths,
and instructions to inspect the relevant source before answering.

## Status

`done` — latest-rule synchronization, document preparation, validation and
migration pass the behavioral suite. Independent review and current-upstream
structural validation pass. Target-project tests remain unexecuted; this
preflight does not certify full eatmycode release compliance.

## Code Structure

| File | Role |
| ---- | ---- |
| `architecture.py` | Upstream refresh, document proposals, structural checks, migration, and allowed writes |
| `gameplans/architecture_docs.md` | Three phases and the strict documentation result contract |
| `personas/docs_planner.md` | Principal architect responsible for subsystem ownership and planning |
| `personas/docs_writer.md` | Senior engineer and technical writer responsible for document proposals |
| `personas/docs_verifier.md` | Independent reviewer responsible for source accuracy and acceptance |

## Key Types and Entry Points

- `architecture.py:43` — `Skill` carries the fetched revision, specification,
  and verbatim shared sections.
- `architecture.py:56` — `Report.context()` supplies authoritative root
  documentation and module paths, with the test-execution limitation.
- `architecture.py:111` — `sync_skill()` clones the fixed eatmycode origin if
  absent and fetches its default `HEAD` on every run. Dirty caches, refresh
  failures, and unsupported contract changes stop the review; stale cached
  rules are never accepted silently.
- `architecture.py:171` — `_canonicalize()` installs the current Development
  Loop, Coding Discipline, and Review Checks before the Index, retaining
  explicitly named project deviations.
- `architecture.py:221` — `validate_documents()` checks the full proposed set
  before writes: allowed paths, shared blocks, module headings, Index coverage,
  confined link targets, source paths, line references, and test-command blocks.
- `architecture.py:307` — `_preserve_guidance()` archives regular agent guidance
  verbatim and retains prior archives across later root-document rewrites.
- `architecture.py:325` — `_apply()` stages all artifacts and rolls back applied
  replacements if an I/O operation fails.
- `architecture.py:367` — `prepare()` always invokes the source audit, even for
  existing documents, then validates and applies an accepted proposal.

## Interactions

[review-cli.md](review-cli.md) supplies a script-owned detached workspace and
the documentation-session callback. [git-io.md](git-io.md) owns Git operations
and preserves the target repository's source checkout. Generated documentation
remains a local review artifact in that workspace; this module never commits
or pushes it.

[harness.md](harness.md) binds read-only tools to DocsPlanner, DocsWriter, and
DocsVerifier. Every role speaks in `plan`, `draft`, and `verify`; only the
writer drafts, and the verifier independently accepts or rejects the final
proposal. The model returns `documents`, `audited`, and `summary`. Coverage of
real subsystems and semantic accuracy require this source audit in addition to
the host's structural validation.

The host writes only `ARCHITECTURE.md`, direct `ARCHITECTURE/*.md`
documents, and root `AGENT.md`, `AGENTS.md`, and `CLAUDE.md` symlinks targeting
the control center. Existing regular agent guidance survives inside fenced
archives, whose historical references are excluded from current-source checks.
Output paths cannot traverse symlinks. [prompts.md](prompts.md) combines the
result with case-specific review instructions.

## How to Test

Run from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile architecture.py
```

Passing evidence is exit code zero, an `OK` unittest summary, and no compiler
diagnostics. `tests/test_architecture.py` owns preflight behavior, including
refresh failures, rejected proposals, preserved guidance, and write rollback.
These commands test this tool. Target-project test commands described by
generated documentation remain unexecuted during a review.

## Open Gaps / Roadmap

- A changed upstream workflow or module contract requires an explicit
  integration update. Only wording inside the three shared sections updates
  automatically; the remaining specification is checked by fingerprint.
- Semantic coverage depends on model inspection. The host proves structure
  and path/reference validity; source audit alone cannot prove runtime behavior.
- Writes roll back recoverable I/O failures; they are not a filesystem-wide
  transaction against process termination or power loss.
