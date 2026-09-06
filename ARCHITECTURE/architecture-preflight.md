---
eatmycode_version: "1.1.0"
---
# Architecture preflight

## Goal

Prepare current, source-backed architecture after item identification and
selected-branch source preparation, including any local PR merge (M1).
Own specification refresh, freshness checks, audited proposals, structural
validation and local document migration. Panels supply source evidence; this
owner never runs target commands, reviews a PR or publishes a report.

## Status

`done` — refresh, current-document reuse, validation, preservation and rollback are implemented
and covered by the offline behavioral suite. Current eatmycode integration
supports stable version metadata, the ordered root contract and ten module
sections. Source audits do not prove target tests passed or full eatmycode
release compliance; no target commands run during preparation.

## Code Structure

| File | Role |
| ---- | ---- |
| `architecture.py` | Upstream refresh, version gate, document validation, migration and allowed writes |
| `gameplans/architecture_docs.md` | Documentation phases and strict result contract |
| `personas/docs_planner.md` | Source ownership inventory and migration planning |
| `personas/docs_writer.md` | Complete current-contract document proposals |
| `personas/docs_verifier.md` | Independent source audit and acceptance |
| `tests/test_architecture.py` | Freshness, proposal, preservation and filesystem boundary regressions |

## Language and Conventions

Python follows the [root conventions](../ARCHITECTURE.md#coding-style-and-code-design);
gameplans use YAML frontmatter and Markdown, and personas use Markdown.
`Skill` and `Report` are frozen dataclasses. Invalid source/document boundaries
raise `ArchitectureError`; I/O errors propagate to the CLI. `_sections` ignores
fenced examples when finding actual headers (`architecture.py:102`). Reuse
these parsers and the shared-heading constants instead of duplicating Markdown
rules in callers. No local formatter or type-checker configuration exists.

## Design and Invariants

After the selected source is ready, the workflow fetches the fixed upstream
default `HEAD` through Git once per review. The
supported-contract fingerprint excludes only the three verbatim shared blocks;
unknown workflow/template changes still stop preflight. `Skill.version` comes
from valid stable SemVer in the supported specification's `metadata.version`.

`reuse_current` reads only the bounded, regular root `ARCHITECTURE.md` and
compares its version as an integer triple. A matching version immediately
returns `Report.audited=False` with the root text. It never enumerates modules,
validates structure, links or references, reads agent guidance, creates a
documentation worktree, or calls the panel. Module state and regular agent files
cannot send a current root back into preparation. The selected or merged source snapshot
also serves as its guide; panel file-access boundaries still apply.

A missing root or missing, invalid or older root version requires reconciling
the full set. A newer root stops without changes. Once preparation is needed,
newer module versions also stop rather than being downgraded. Root path safety
and I/O errors propagate. Generated version stamps are accepted only after the
panel audit and host validation; the host never invents stamps.

The merged final set must have exact ordered root/module headers, verbatim
shared sections, Index coverage, valid confined links, real source paths and
line references, and fenced test commands. Small modules may use one load-bearing
reference; ten is the maximum. Semantic ownership, source accuracy and the
coding-only content rule require source inspection beyond these structural
checks. Reuse bypasses all these checks and does not prove content freshness;
the context discloses that only the root version was checked and requires the
PR/issue panel to inspect full relevant source. Upstream refresh remains mandatory.

Only root `ARCHITECTURE.md` and direct owning modules are model proposal paths.
`documents` maps paths to complete Markdown; omission retains a file, and
`null` can remove only an existing direct module. The panel may remove modules
devoted to non-coding guidance and must repair links/Index entries; the host
rejects root deletion and references to removed documents. It preserves the
originals of changed/removed documents and regular agent files as fenced snapshots
in host-controlled root `ARCHITECTURE-ARCHIVE.md`, outside the architecture set.
The panel migrates durable coding rules into current documents. Symlink escapes
are refused. All replacements, archives, removals and agent-entry symlinks are
staged together and rolled back on recoverable write failure.

## Key Types and Entry Points

- `architecture.py:50` — `Skill`: immutable fetched revision, full specification,
  canonical shared sections and stable semantic version.
- `architecture.py:58` — `Report`: changed paths, final documents, summary and
  whether a source audit ran; `context()` exposes the guide and inspection limits.
- `architecture.py:126` — `_version`: parse supported YAML frontmatter into an
  integer triple, returning `None` for missing or invalid stable SemVer.
- `architecture.py:146` — `sync_skill`: refresh the fixed origin, reject dirty,
  stale/unavailable or unsupported rules, and return the verified `Skill`.
- `architecture.py:195` — `reuse_current`: check only root version and return
  a report for reuse, `None` when preparation is needed, or an error for a newer root.
- `architecture.py:232` — `_canonicalize`: install upstream shared blocks in
  order before Index, retaining explicitly named project deviations.
- `architecture.py:283` — `validate_documents`: validate the entire retained
  proposal and removed-reference set without changing the checkout.
- `architecture.py:376` — `_archive`: preserve original text outside coding
  docs, retaining prior snapshots and refusing unsafe/oversized archive files.
- `architecture.py:396` — `_apply`: stage replacements, removals and symlinks,
  restore prior artifacts after I/O failure, and return changed paths.
- `architecture.py:440` — `prepare`: gate the root version, skip preparation or
  audit and merge proposals, validate, archive and apply; return a `Report`.

## Interactions

[Workflow](review-cli.md) calls `reuse_current` once on the final selected-branch
or locally merged PR source before creating a documentation worktree. If
preparation is needed, it supplies a separate retained worktree and a generation
callback. [Git](git-io.md) owns
transport, isolated sources and guide worktrees. Citations use the selected or
merged source; generated guide edits remain separate.

[Harness](harness.md) supplies DocsPlanner, DocsWriter and DocsVerifier, each
speaking in `plan`, `draft` and `verify`. Only the writer drafts. The verifier's
attributed final `DOCS_AUDIT` record and the chair's `audited` field must both
accept the proposal. The result fields remain `documents`, `audited`, `summary`;
`documents` values admit Markdown or permitted `null` removals. Archive content
is excluded from `Report.documents` and generated-guide read grants.

The model has only source-inspection tools. After an audit, host code creates root `AGENT.md`,
`AGENTS.md` and `CLAUDE.md` symlinks to the control center after validation and
preservation. [Profiles](prompts.md) supplement the resulting case context.
The preflight suite tests the document boundary; workflow integration tests
exercise the real scripted documentation panel and independent veto.

## How to Test

Run from the repository root with the pinned kerness dependency installed:

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile architecture.py
```

Passing evidence is exit zero, an `OK` unittest summary, and no compiler
diagnostics. The refresh test creates a temporary Git upstream with a minimal
synthetic specification. It proves initial cloning, changed rules and revisions,
fetching even without changes, and rejection of dirty caches, failed fetches and
unsupported contracts. No upstream specification snapshot is bundled.
`tests/test_architecture.py` also owns root-version reuse and stale-root fallback,
invalid proposals, guidance preservation, module removals and rollback.
`tests/test_workflow.py` owns reuse/audit progress and session delegation, real
scripted panel participation and rejection. Generated target documentation may list test
commands, but the review tool never executes them or certifies their success.

Check compatibility with the actual latest upstream separately, with network
access. This uses the runtime refresh path and a temporary cache:

```sh
.venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
import architecture

with TemporaryDirectory() as directory:
    skill = architecture.sync_skill(Path(directory) / "eatmycode")
    print(skill.version, skill.revision)
PY
```

Expected: exit zero and the fetched version/revision. An unavailable or
unsupported upstream stops the check; local test data cannot substitute for it.

## Review and Refactor Guide

An upstream contract update requires inspecting the full current specification,
`sync_skill`, `prepare`, `validate_documents`, gameplan and three personas;
changing only the fingerprint is insufficient. Run the live compatibility check
and retain rejection coverage for unsupported changes. Version changes
must preserve newer documents and audit stale content before stamping.

Migration changes require reviewing `_document_path`, `_archive`, `_apply` and
removed-reference checks together. Extend the owning preservation/rollback cases
rather than bypassing validation for legacy content. Archive paths remain host
controlled and outside generated guide grants. Preserve separate source
repositories and generated guide worktrees, no target execution, and independent
audit acceptance.

## Open Gaps / Roadmap

- M1: future upstream workflow/template changes need explicit integration review;
  only wording inside the three shared sections updates automatically.
- Semantic subsystem coverage and coding-only scope rely on source inspection;
  generated docs pass host structure/reference checks, not factual interpretation
  or target runtime behavior. Reused docs have only their root version checked;
  their modules, structure and content may be stale or incomplete.
- Rollback covers recoverable I/O errors, not process termination or power loss.
- Archives are bounded by the document size limit and retained across audits;
  no archive compaction or automated retention policy is implemented.
