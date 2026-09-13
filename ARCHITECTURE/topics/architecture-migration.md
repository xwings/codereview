---
eatmycode_version: "2.0.0"
---
# Architecture migration and local writes

Owner: [Architecture preflight](../modules/architecture-preflight.md)

Read when: changing documentation proposal validation, architecture layout,
retained/removal semantics, guidance archives, agent aliases or atomic local writes.

## Contract

The source checkout remains authoritative. Documentation changes are retained
in a separate guide worktree; no commit or push occurs. Models have read-only
inspection tools and return `documents`, `audited`, `summary`. The `documents`
map holds complete replacements; omitted files remain, and `null` removes only
existing permitted non-root documents. Validate the combined retained set, not
just changed entries (`architecture.prepare`, `validate_documents`). The host
supplies canonical AGENT_RULES when omitted; an explicit rules proposal must
match verbatim.

Allowed final pages are `ARCHITECTURE.md`, `ARCHITECTURE/AGENT_RULES.md`, and
flat lowercase kebab-case Markdown under `ARCHITECTURE/modules/`, `topics/` or
`indexes/`. Legacy pages may be inspected/removed while migrating, but cannot
remain as alternate layouts. The root uses ordered Read First, Project Snapshot,
System Design, Code Conventions, Verification and Task Index sections. Its
mandatory Read First text is copied verbatim. AGENT_RULES alone contains the
complete fetched Development Loop, Coding Discipline and Review Checks verbatim;
project additions stay in fact owners. Modules have the exact eight contract
sections; topics have Contract, Change and Verify, Evidence and Gaps; indexes
have Routes. Root has at most 8 task rows, index pages at most 12 routes.

Every page needs its prescribed title, owner backlink and reading condition,
with an incoming conditional route reachable from root. Index routes narrow
ownership and cannot cycle. Modules own real subsystems; topics expand a named
contract rather than serving as arbitrary continuations. Source and local-link
references must resolve, including anchors; deleted-page references fail. Five
must-read module symbols is the authoring ceiling. Semantics, subsystem coverage,
coding-only scope and durable guidance require independent source audit beyond
mechanical structure checks.

Refresh content before stamps. Missing/stale root requires a whole-set source
reconciliation in batches; stale pages require affected owners/routes. Preserve
newer versions. Shared guidance has one canonical home; avoid copied command
lists, full inventories and completed roadmap logs. Excluded non-coding pages
are removed with repaired routes; useful mixed-file coding facts survive in
their owner. Required additions cannot be hidden behind unrelated triggers.

Before replacing/removing docs or regular root agent files, preserve original
text as fenced snapshots in host-controlled `ARCHITECTURE-ARCHIVE.md`. This
historical archive is outside active architecture and generated-guide grants.
Move durable coding guidance into appropriate fact owners before replacing
root `AGENT.md`, `AGENTS.md`, `CLAUDE.md` with relative aliases to the root.
Nested agent files retain their scope. The panel cannot propose archive/alias
writes directly. Reject path/symlink escapes and oversized originals/archives.

Stage replacements, removals, necessary directories, archive and aliases
together; recoverable write failure restores previous artifacts. Root removal,
links to removed files, malformed proposals or rejected independent audit stop
before writing. Retained original guidance is not permission to expose archives
to later review panels (`architecture._archive`, `_apply`).

## Change and Verify

Read the [preflight owner](../modules/architecture-preflight.md) for upstream,
freshness, limits and exact checks. If layout changes, read
[panels](../modules/harness.md) for individual guide grants and
[workflow](../modules/review-cli.md) for separate citation source. For worktree
changes also read [Git](../modules/git-io.md).

Run the owner's architecture suite and root integration checks. Extend existing
proposal, retained-file, removed-reference, archive, alias, symlink and rollback
cases for changed behavior. Verify size/layout/stamps for the entire set and
read source per owner; valid references alone do not certify their claims.
Walk one affected module route and a crossing source/guide boundary to ensure
new paths remain discoverable without loading every document.

## Evidence and Gaps

`gameplans/architecture_docs.md` and `personas/docs_*.md` define source-audit
responsibility; `tests/test_architecture.py` covers mechanical acceptance and
filesystem preservation. `tests/test_workflow.py` checks authenticated vetoes
and generated-file access. No target tests run. Recoverable rollback does not
cover process termination or power loss; archive compaction is unimplemented.
