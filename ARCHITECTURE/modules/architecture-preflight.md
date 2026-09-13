---
eatmycode_version: "2.0.0"
---
# Architecture preflight

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `architecture.py`, `gameplans/architecture_docs.md`,
`personas/docs_*.md`, target guide freshness/migration, documentation validation
or this project's architecture contract.

## Responsibility and Status

Prepare source-backed architecture after item identification and final
selected-branch/local-merge source preparation. Own upstream refresh, freshness,
contract checks, independently audited proposals and validated local writes.
`done` — implemented; the current separated/routed contract is covered by offline checks.
Target commands never execute, so source audits cannot certify target tests or
full release compliance.

## Code Map

| Path / symbol | Role |
| ------------- | ---- |
| `architecture.py:sync_skill` | Fresh upstream rules and stable semantic version |
| `architecture.py:reuse_current` | Mechanical whole-set freshness/layout gate |
| `architecture.py:Report.context` | Compact startup context and inspection limits |
| `architecture.py:validate_documents`, `prepare` | Validate retained proposals, preserve/apply local guidance |
| `gameplans/architecture_docs.md`, `personas/docs_*.md`, `tests/test_architecture.py` | Role contracts, source audit, temporary-upstream/filesystem regressions |

## Local Conventions

Use [root conventions](../../ARCHITECTURE.md#code-conventions). `Skill`/`Report`
are frozen dataclasses; invalid source/document boundaries raise
`ArchitectureError`. `_sections` ignores fenced example headings. Reuse shared
heading/limit/path parsers instead of caller-specific Markdown rules. No local
checker config exists.

## Contracts and Invariants

`sync_skill` fetches the default `HEAD` from `https://github.com/xwings/eatmycode.git`
through Git on every run. Cache origin/cleanliness must match. Unavailable or
malformed upstream stops review; neither a cached release number nor remembered
fingerprint selects active rules. `metadata.version` supplies stable SemVer,
compared as integer components, and fetched text supplies shared instructions. Required separated-contract
sections and the prescribed Read First block must be present in the skill.

Mechanically inspect root and every recursive architecture Markdown before
loading stale bodies into model context. The contract has one compact root,
mandatory `ARCHITECTURE/AGENT_RULES.md`, flat kebab-case modules/topics/indexes.
Hard Unicode-character limits are 6,000/12,000/8,000/6,000/4,000 respectively;
count whole UTF-8 text including frontmatter/line endings. Exactly at a limit
passes. A separate 2 MiB input/archive cap protects legacy reads, not document
authoring. Confined regular files/directories are required.

Missing, invalid or older root requires complete reconciliation in owner
batches. Stale individual pages require affected owners/routes; oversized or
invalid layout needs repair. Any newer recorded version takes precedence:
preserve it and stop rather than downgrade. Matching docs pass host layout, size, ordered section, canonical rules/Read
First, route limits, owner/trigger, link/anchor, reachability and index-cycle
checks before skipping the model documentation audit. Source-reference checks
and semantic audit are skipped on reuse and disclosed; review still verifies
task-relevant claims against source. A stamp cannot establish
complete subsystem coverage or factual accuracy.

The docs-only `architecture_inventory` tool pages metadata for at most 40 files
per call (version/kind/characters, plus totals, maxima and layout/size anomaly
count), without bodies. Review startup includes root and mandatory rules, not
a wholesale module/file inventory. Root Task Index routes source prefixes and change triggers; match
only necessary index branches, owners and topics, and follow partners only for
affected boundaries. Full migrations audit the complete scope in bounded
batches; mechanical summaries stay compact (`Report.context`, `prepare`).

Documentation specialists plan, draft and independently audit through
`plan`/`draft`/`verify`; only DocsWriter drafts. Final DocsVerifier must accept
with `DOCS_AUDIT`, and Chair's `audited` must also be true. The host validates
the complete retained proposal before writing. Content precedes stamps, root
certification comes last, and all architecture files must agree after migration.
Read [architecture migration](../topics/architecture-migration.md) for proposal
schema, generated-file layout, link validation, preservation, aliases or rollback
changes; those filesystem invariants are mandatory for such changes.

## Dependencies and Boundaries

[Workflow](review-cli.md) decides source reuse versus separate guide worktree;
read it for preflight order/context changes. [Git](git-io.md) owns cache transport
and source/guide creation; read it for lifecycle changes. [Panels](harness.md)
owns independent audit participation and named guide grants; read it when docs
schema or layout affects runtime access. Citation source always remains the
unmodified selected/merged checkout. Profiles cannot select freshness rules.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| -------------- | ---------------- | ---------------------- |
| Upstream/freshness | `sync_skill`, `reuse_current`; temporary-upstream/version cases | Workflow; current live upstream check below |
| Contract/routing/context | Fetched specification, validation/context and docs personas | Panels/Prompts; size/layout/rules/routing cases |
| Migration/removal/writes | `prepare`, archive/apply helpers; preservation/rollback cases | Migration topic, Git and Panels for guide access |
| Own architecture refresh | Root, matching owners/source in batches | Whole-set shape/links/stamps and representative route walks |

## Verification

From repository root with the installed binding, run
`.venv/bin/python -m unittest discover -s tests -p 'test_architecture.py' -v`.
Expect `OK`, exit 0. Temporary upstreams exercise refresh, changed rules, dirty
cache/fetch/malformed-spec failures; version/size/layout cases exercise reuse
and migration; retained proposals, guidance preservation and rollback cases
prove failed preparation leaves originals intact. [Root checks](../../ARCHITECTURE.md#verification)
add scripted real documentation panels, independent vetoes and guide access.

Verify actual upstream compatibility with network access, from repository root:

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

Expect exit 0 and fetched metadata version/revision. This proves current rule
refresh only; it executes no target code or model audit. Architecture changes
also require exact headings/Read First/shared rules, reachability/links/anchors,
source evidence, complete ownership, layout, sizes and stamp agreement; walk
representative local and cross-owner tasks without loading unrelated modules.

## Known Gaps

Structural validity and current stamps cannot establish source semantics or
model reading compliance. Future specifications may add semantics beyond host
checks. Cache access is not serialized across concurrent runs. Rollback covers
recoverable I/O failure, not process termination/power loss. Historical archives
are bounded but have no compaction policy. No additional milestone is accepted.
