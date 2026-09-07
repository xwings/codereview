---
eatmycode_version: "1.2.0"
---
# Architecture preflight

## Goal

Prepare current, source-backed architecture after item identification and
selected-branch source preparation, including any local PR merge (M1).
Own latest-specification refresh, recursive freshness and size checks, audited
proposals, structural validation and local documentation migration. Panels
supply source evidence; this owner never runs target commands or publishes.

## Status

`done` — latest-specification refresh, recursive version and size gates,
current-document reuse, validation, preservation and rollback are implemented
and covered by the offline behavioral suite. A separate live check exercises
actual upstream refresh. Source audits do not prove target tests passed or
full eatmycode development compliance; no target commands run in preparation.

## Code Structure

| File | Role |
| ---- | ---- |
| `architecture.py` | Upstream refresh, version/size gate, validation, migration and allowed writes |
| `gameplans/architecture_docs.md` | Documentation phases and strict result contract |
| `personas/docs_planner.md` | Source ownership inventory and migration planning |
| `personas/docs_writer.md` | Complete current-contract document proposals |
| `personas/docs_verifier.md` | Independent source audit and acceptance |
| `tests/test_architecture.py` | Dynamic refresh, recursive freshness, preservation and filesystem regressions |

## Language and Conventions

Python follows the [root conventions](../ARCHITECTURE.md#coding-style-and-code-design);
gameplans use YAML frontmatter and Markdown, and personas use Markdown.
`Skill` and `Report` are frozen dataclasses. Invalid source/document boundaries
raise `ArchitectureError`; I/O errors propagate to the CLI. `_sections` ignores
fenced examples when finding actual headers (`architecture.py:97`). Reuse
these parsers and shared-heading constants instead of duplicating Markdown
rules in callers. No local formatter or type-checker configuration exists.

## Design and Invariants

After the final source is ready, `sync_skill` fetches the default `HEAD` from
`https://github.com/xwings/eatmycode.git` on every invocation through
[Git I/O](git-io.md). The cache origin and cleanliness must match before reuse;
fetch failures stop the run. The fetched `SKILL.md` supplies `metadata.version`
and the shared rules delivered to the documentation panel. Release numbers
and a stored content fingerprint do not constrain which revision is current.
The active version must be valid stable SemVer, compared as integer components;
missing or malformed required skill content is an error.

`reuse_current` inventories `ARCHITECTURE.md` and every Markdown file recursively
under `ARCHITECTURE/`, including owning modules and supporting pages. Each must
record the fetched version and contain at most 35,000 Unicode code points,
including frontmatter, whitespace and line endings. Exactly 35,000 passes.
A separate 2 MiB input/archive limit protects reads of legacy documents and
historical snapshots; larger inputs stop before preparation. It does not
replace the character count. Files and directory components must respect the confined
regular-file boundary.

| Observed architecture | Preflight behavior |
| ---- | ---- |
| Root plus at least one recursive Markdown page exist, all versions match and files fit | Reuse the source snapshot as its guide without a documentation model call. |
| Missing root, or missing/invalid/older root version | Audit and reconcile the complete set in a retained local guide worktree. |
| Missing/invalid/older module or supporting-page version | Refresh stale content and affected owners/links in the guide worktree. |
| Any architecture file exceeds 35,000 characters | Prepare a split or concise update before the set can pass. |
| Any recorded version is newer than the active skill | Stop, preserving versions and structure; never downgrade. |

A matching inventory returns `Report.audited=False` and all inventoried
documents. This path does not check semantic freshness, root/module sections,
links, source references or agent guidance, and does not create a guide
worktree. Its context discloses those limits and requires the PR/issue panel
to inspect the full relevant source. Regular agent files do not independently
trigger preparation. A matching stamp does not prove a missing subsystem has
been documented, or detect a deleted page still named by an Index link; source
coverage and link integrity are checked during an actual audit.

When preparation is needed, the documentation panel receives the complete
fetched skill and an inventory of readable current documents and regular agent
guidance. A missing or stale
root requires the whole set; stale pages require their content and affected
owners to be reconciled. Content and structure come before stamps. Newer
versions take precedence over migration, including when the root is missing.
The host accepts current stamps only after independent panel acceptance and
validation of the complete retained proposal.

Generated paths are the root `ARCHITECTURE.md` and nested Markdown files under
`ARCHITECTURE/`. The `documents` map contains complete replacements; omission
retains a file, and `null` removes only an existing non-root document. Owning
modules follow the Module Template; supporting and index pages use appropriate
headings and link back to their root or owner. Root Index links must make the
set reachable, directly or through linked pages. Splitting oversized documents
must preserve owner routing and source references.

Host validation checks versions, sizes, ordered root/module headers, verbatim
shared sections, document reachability, confined links, real source paths and
line references, and fenced module test commands. Modules use at most ten key
entry-point references. The independent source audit checks factual accuracy,
subsystem ownership, useful retained guidance and coding-only scope. These
semantic checks cannot be established by a valid path or existing line alone.

Before replacing or removing documents and regular agent files, the host
preserves their original text as fenced snapshots in its root-controlled
`ARCHITECTURE-ARCHIVE.md`. This historical guidance archive is outside the
active architecture set and outside generated-guide read grants. The writer
migrates durable coding rules into the active documents and repairs links when
removing non-coding-only pages. Root deletion and links to removed pages fail
validation. Symlink escapes are refused. Replacements, nested directories,
archives, removals and root agent symlinks are staged together; recoverable
write failure restores prior artifacts.

## Key Types and Entry Points

- `architecture.py:46` — `Skill`: immutable fetched revision, complete skill
  text, canonical shared sections and stable semantic version.
- `architecture.py:54` — `Report`: changed paths, inventoried final documents,
  summary and audit status; `context()` exposes the guide and inspection limits.
- `architecture.py:114` — `_version`: parse version frontmatter into an integer
  triple; missing or invalid stable SemVer returns `None`.
- `architecture.py:140` — `sync_skill`: refresh the fixed upstream, reject dirty
  or unavailable rules and malformed metadata, and return the fetched `Skill`.
- `architecture.py:189` — `reuse_current`: inventory recursive document versions
  and sizes; return a reuse report, `None` for preparation, or a preservation error.
- `architecture.py:235` — `_canonicalize`: install upstream shared blocks in
  order before Index, retaining explicitly named project deviations.
- `architecture.py:300` — `validate_documents`: check the complete retained
  proposal and removed-reference set without changing the checkout.
- `architecture.py:415` — `_archive`: preserve historical originals outside
  active docs, retaining prior snapshots and refusing unsafe/oversized archives.
- `architecture.py:435` — `_apply`: stage replacements, removals and symlinks,
  restore prior artifacts on I/O failure, and return changed paths.
- `architecture.py:486` — `prepare`: reuse or audit, merge proposals, validate,
  archive and apply locally; return a `Report`.

## Interactions

[Workflow](review-cli.md) calls `reuse_current` on the selected-branch or locally
merged PR source before deciding whether to create a documentation worktree.
If preparation is needed, it supplies a retained worktree and generation
callback. [Git](git-io.md) owns transport, isolated sources and guide worktrees.
Citations continue to use the source snapshot; generated edits are separate.

[Harness](harness.md) supplies DocsPlanner, DocsWriter and DocsVerifier in
`plan`, `draft` and `verify`. Only the writer drafts. The actual final verifier
turn must accept through `DOCS_AUDIT`, and the chair's `audited` field must also
be true. Result fields remain `documents`, `audited`, `summary`; document
values admit Markdown or permitted `null` removals. The model has only
source-inspection tools. Host code installs root `AGENT.md`, `AGENTS.md` and
`CLAUDE.md` symlinks after validation and preservation. [Profiles](prompts.md)
supplement case context without controlling preflight freshness.

The preflight tests exercise the document boundary; workflow integration tests
exercise real scripted documentation panels, reuse, progress, recursive guide
access and independent rejection. Test document templates take their stamps from
the supplied `Skill.version`; explicit synthetic releases exercise version
ordering and upstream changes offline. The CLI never imports or executes these
tests during a review.

## How to Test

Run from the repository root with the pinned kerness dependency installed:

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile architecture.py
```

Passing evidence is exit zero, an `OK` unittest summary and no compiler
diagnostics. Temporary Git upstreams prove cloning, fetching unchanged and
changed revisions, metadata/shared-rule updates, and rejection of dirty caches,
failed fetches and malformed specifications. Recursive gate tests cover current
reuse, stale/missing/invalid/newer versions, size boundaries and nested pages.
Proposal, guidance preservation, removal and rollback cases prove that failed
preparation leaves original data intact. `tests/test_workflow.py` supplies
scripted real-panel participation and veto evidence without model services or
GitHub writes. Target test commands are documented but never executed.

Check actual latest upstream with network access using the runtime refresh path
and a temporary cache:

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

Expected: exit zero and the fetched metadata version/revision. Network or
malformed-upstream failures cannot be covered up with cached rules or an offline
fixture. This check fetches rules; it does not run a target test or model audit.

## Review and Refactor Guide

Refresh behavior belongs in `sync_skill`, `reuse_current` and `prepare`.
Preserve dynamic upstream selection, stable SemVer ordering, newer-version
protection and recursive size checks. Test refreshes with changed synthetic
releases and run the live check; a test fixture must not become a runtime
version allowlist. Schema interpretation changes also require reading the
complete fetched specification, `validate_documents`, documentation gameplan
and three personas.

Migration changes require inspecting path confinement, archive preservation,
`_apply`, reachability and removed-reference checks together. Extend owning
preservation/rollback cases instead of bypassing validation. New supporting
pages must be accessible through individual guide grants in
[session construction](harness.md), while archives and unrelated guide-worktree
files remain inaccessible. Preserve separate citation sources, no target
execution and independent audit acceptance.

## Open Gaps / Roadmap

- M1's latest-skill and recursive freshness behavior is implemented. Future
  specifications can require semantics beyond current structural checks;
  the fetched rules and independent source audit remain necessary evidence.
- Reused docs have current versions and sizes, but may have stale content or
  missing ownership. Source inspection remains required in every review.
- Rollback covers recoverable I/O errors, not process termination or power loss.
- Historical archives retain a bounded byte size with no compaction policy.
- The shared specification cache is not serialized across simultaneous runs.
