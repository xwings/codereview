---
name: eatmycode
description: Create, audit, or maintain agent-readable architecture docs and guide autonomous planning, coding, review, verification, and improvement until a change is ready for public or production release.
metadata:
  version: "1.1.0"
---

# eatmycode

Build and maintain an architecture reference for coding agents, then use
it to write, review, verify, improve, and refactor code. Repository code,
configuration, and explicit project requirements remain authoritative.

## Version and Freshness Gate

On **every invocation**, before using architecture docs to plan, code,
review, improve, or refactor:

1. Read `metadata.version` from the active `SKILL.md`. This is the
   current skill contract; do not infer it from memory or an online
   release. Releases use stable SemVer (`MAJOR.MINOR.PATCH`). Compare
   integer components, never strings or file modification dates.
2. Read `eatmycode_version` from YAML frontmatter at the start of
   `ARCHITECTURE.md` and every `ARCHITECTURE/<module>.md`. Read module
   metadata first; load full module content only when relevant or stale.
3. Apply the following decision before relying on the docs:

   | Evidence | Required action |
   | -------- | --------------- |
   | No architecture docs | Create the doc set under the current contract. |
   | Root missing, or root version absent, invalid, or older | Treat the entire existing doc set as stale; reconcile root and all modules with source and the current contract. |
   | Module version absent, invalid, or older | Refresh that module and its Index entry; the root cannot certify the set until all modules are current. |
   | Versions match | Inspect the task's source, configuration, tests, and relevant docs for drift or non-coding content; correct stale claims and remove excluded content before using them. Otherwise, reuse the docs without rewriting unless a refresh was requested. |
   | User explicitly requests refresh | Refresh the requested scope even when versions match; a general refresh covers the whole set. |
   | Any recorded version is newer than the active skill | Preserve it and its newer structure. Use a matching or newer skill if available; otherwise report the mismatch, work from source, and leave contract migration pending. Never downgrade or stamp it with an older version. |

   A newer-version mismatch takes precedence over the other migration
   actions. If the active skill has no valid version, report that the
   contract cannot be verified; do not invent or write a version stamp.
4. Refresh **content**, not just metadata: inspect source, fill newly
   required sections, reconcile conventions and contracts, remove
   non-coding content under the Output Contract, replace stale shared
   sections from this skill, and repair links and references. Preserve
   durable coding guidance and justified deviations. Do not use an
   outdated claim to decide a change while its refresh is pending.
5. After content and structural verification pass, record the active
   version in each refreshed file. Stamp the root only after every module
   satisfies the current contract, then verify that the stamps agree.
   Keep existing stamps during edits; leave new files unstamped until
   verified. An interrupted or partial migration must not claim completion.

Every verified root and module file starts with this frontmatter,
substituting the actual active version. This example is final output:

```yaml
---
eatmycode_version: "<active SKILL.md metadata.version>"
---
```

`metadata.version` is the single release-version source in this skill.
Bump it when changing the skill: major for incompatible output/workflow
contracts, minor for compatible requirements or capabilities, patch for
clarifications and fixes. Any older architecture stamp triggers the gate,
including a patch difference. Unversioned docs are legacy docs to migrate.

## Output Contract

- `ARCHITECTURE.md` and `ARCHITECTURE/` contain coding context only.
  Every item must help an agent locate, understand, write, review, debug,
  test, improve, or refactor code. Use concise facts, tables, exact
  development commands, source paths, symbols, and links.
- Exclude non-coding material: deployment/publishing guides, production
  runbooks, infrastructure operation instructions, business plans,
  project administration, and human onboarding or user tutorials. Keep
  such material outside the architecture doc set.
- During creation, refresh, audit, or maintenance, remove excluded
  content encountered in root and module docs. Remove files devoted
  entirely to non-coding guidance and their Index entries; repair links.
  In mixed documents, retain only the coding context. A full refresh or
  content-scope audit inspects the entire architecture doc set.
- Judge content by its purpose. Source-level runtime behavior, failure
  handling, configuration contracts, infrastructure/tooling code design,
  and build/test prerequisites belong here when they inform code changes.
  Deployment procedures and live-environment inventories do not. A
  subsystem implemented in deployment tooling can still own a module doc.
- `ARCHITECTURE.md` owns cross-cutting facts and rules, follows the Root
  Contract below, and routes tasks through an Index of `ARCHITECTURE/`.
- `ARCHITECTURE/<module>.md` owns one subsystem and follows the Module
  Template below exactly. Do not duplicate its prose in the control
  center; cross-link it.
- Cite authoritative configs or representative `file:line` precedents
  for conventions and constraints. Distinguish required rules, observed
  implementation, and proposed changes. If evidence is missing, state
  what was inspected and what remains unknown; never invent a standard,
  design rationale, language version, or milestone. Use `not applicable`
  with a reason when a required topic does not apply.
- Existing regular `AGENT.md`, `AGENTS.md`, and `CLAUDE.md` files are
  bootstrap source. Migrate their durable coding guidance into
  architecture and preserve useful non-coding guidance elsewhere before
  replacing them with symlinks to `ARCHITECTURE.md`. If absent, create
  the symlink names used by the project or harness.
- Copy the `## Development Loop`, `## Coding Discipline`, and
  `## Review Checks` sections below into every generated
  `ARCHITECTURE.md`, verbatim and in that order, before the Index. Module
  files do not repeat them.
- Project-specific exceptions go under `### Project-Specific Deviations`
  after the affected shared section. They may strengthen the Definition
  of Done; never weaken or edit the shared text.

## Root Contract

After version frontmatter and the project title, include these level-two
(`##`) sections in order. Keep only project-wide coding facts here; link
module-specific detail.

| Section | Required agent context |
| ------- | ---------------------- |
| Mission and Constraints | Software purpose, observable behavior, supported platforms, explicit code-scope non-goals, compatibility, and implementation limits. |
| Languages and Toolchain | Languages by source area; language standards, runtimes, frameworks, compilers, package/build tools and supported versions, citing manifests, lockfiles, and CI. Distinguish declared support from locally observed versions. |
| System Design | Subsystems and layers, responsibility and state ownership, allowed dependency directions, forbidden coupling, external/trust boundaries, cross-cutting invariants, and evidence-backed design decisions or ADR links. |
| Runtime and Data Flow | Implemented entry points through ready state, request/job/data paths, persistence, configuration contracts, failure/recovery and shutdown code paths; networking, concurrency, and resource invariants relevant to code changes. |
| Workspace Map | Source, tests, configuration, migrations, generated code, and tooling locations; mark generated/vendor files and their regeneration commands or edit restrictions. |
| Coding Style and Code Design | Formatter/linter/type-checker configs and exact commands; naming, imports, typing, errors, logging, tests, API and abstraction conventions. Cite canonical implementations to reuse; identify inconsistent or unenforced conventions rather than inventing rules. |
| Verification and Review Map | Exact developer setup/local run/build/test/lint/type-check commands, working directories, test prerequisites, CI code checks, and expected evidence. Map code changes to tests, review constraints, compatibility checks, and coverage gaps. Exclude deployment, publishing, and production-operation commands. |
| Roadmap | Current implementation status, coding gaps, and evidence-backed improvement/refactor candidates, affected owners, constraints, and success checks. Separate accepted coding work from proposals; retain established implementation milestone IDs. Exclude business milestones and rollout plans. |

Append `Development Loop`, `Coding Discipline`, and `Review Checks`
verbatim from this skill, then `Index`. Each Index row links the owning
module doc and lists its source paths, responsibility, and tasks or
change triggers that should route an agent there. Include integration
partners where needed to select the next module to read.

Agent reading path: run the freshness gate, read cross-cutting rules,
select owners from the Index, read those module docs and relevant
interaction partners, then inspect the cited code and tests. Avoid
loading unrelated module bodies or duplicating source-code inventories.

## Operating Model

Run four separate roles, using one subagent per role when available or
four distinct labeled passes otherwise:

1. **Planner / Frame** — understand the request, code, docs, and goal;
   define observable success and the plan.
2. **Coder / Write** — make only the planned change.
3. **Tester / Prove** — run behavioral and structural checks; never edit.
4. **Verifier / Review + Gate** — review independently and decide whether
   every release criterion passes; never edit.

Role handoffs are automatic. Do not pause for progress reports, plan
approval, permission to continue, or a review ceremony. Only the Planner
may ask one focused question, and only when a required decision cannot be
found in the request, code, docs, or repository conventions and a wrong
assumption would materially change the result. Otherwise choose the
narrowest repository-consistent interpretation, record it, and continue.

## Architecture Workflow

### 1. Inspect and frame — Planner

Run the Version and Freshness Gate first, then detect the path:

- Existing `ARCHITECTURE.md` or `ARCHITECTURE/` → update or audit in
  place.
- Neither exists → create the doc set.
- Regular `AGENT.md`, `AGENTS.md`, or `CLAUDE.md` → include migration and
  symlink replacement in either path.

Before asking anything, read the root architecture and applicable agent
docs, identify affected subsystems, and inspect their docs and source.
Use a subagent when broad inventory is needed and supported. Never ask
the user to restate discoverable facts.

Perform a distinct planning pass before writing. State the goal and
observable check, active and recorded versions, freshness findings and
migration scope, assumptions, required facts, files and source paths,
Index changes, agent-file migration, symlinks, and verification commands.
Resolve uncertainty from repository evidence. Ask only under the
Operating Model exception; never ask merely for confirmation. When the
plan is sound, continue immediately.

### 2. Create or update — Coder

For a new doc set or contract migration, inspect manifests, build and CI
configuration, formatter/linter rules, representative implementations,
tests, and existing design decisions. Populate the Root Contract and
Module Template from this evidence, including language, coding style,
code design, architecture, and the constraints needed for review and
refactoring.

Import only durable coding content from existing agent files: software
purpose, coding workflow, standards, source layout, development commands,
implementation roadmap, constraints, and known subsystems. Apply the
Output Contract's content filter before migration and symlink replacement.
Drop stale harness boilerplate and duplication. Resolve conflicts from
repository evidence; return to Planner only when a conflict materially
changes the project contract and no source is authoritative.

Create `ARCHITECTURE.md`, add the three shared sections below before its
Index, create one module file per real subsystem, then create agent-file
symlinks only after migration is complete.

For an update or audit, derive for each affected module:

- owned source paths and mission/roadmap goal;
- status: `done`, `in progress (Mx)`, `pending (Mx)`, or `scaffolding`,
  including missing or replacement work;
- up to 10 load-bearing types, functions, commands, or entry points with
  current `file:line` references;
- local language/style conventions, design invariants, public contracts,
  linked upstream/downstream interactions, and refactoring constraints;
- exact test commands and observable passing evidence;
- deferred work, platform gaps, and future milestones.

Patch stale or missing coding material, remove excluded non-coding
content, and update the Index; a contract migration covers all sections
required by the current version, including the copied shared sections.
Follow the freshness gate's stamping rules.
When language/toolchain support, coding conventions, code design,
architecture, ownership, data flow, integration points, module/function
contracts, or public behavior change, update the control center and
owning module doc in the same change.

### 3. Prove, review, and gate — Tester then Verifier

The Tester runs every affected module's **How to Test** commands and the
Verification section below. Each test must prove the module's stated
Status; merely running is insufficient. Every failure becomes an
evidence-backed finding for Coder, as does coverage that Prove finds
missing, duplicated, or obsolete. After every fix, rerun affected tests
and structural checks. Never send a red result to Review.

The Verifier reads full affected files and applies all seven Review
Checks below as separate passes. Every finding cites `file:line`; a check
that did not run does not pass. Verifier returns findings without editing;
Coder fixes only named findings, Tester re-proves, and Verifier
re-reviews. Repeat until the Development Loop's Definition of Done
passes.

## Module Template

Every `ARCHITECTURE/<module>.md` starts with version frontmatter and uses
these exact headers in this order. Keep the content local to this owner;
link root conventions and other owners instead of repeating them.

````markdown
# <Subsystem name>

## Goal

State what this subsystem owns, what it must not own, and which roadmap
milestone (`M1`..`Mx`) it serves when one exists. Identify infrastructure
or scaffolding and avoid inventing milestones.

## Status

Use one status and explain missing or replacement work:

- `done` — implemented; **How to Test** passes.
- `in progress (Mx)` — partially implemented.
- `pending (Mx)` — not started.
- `scaffolding` — works today but will be replaced; state by what and
  when.

Omit the milestone suffix when none is established. Include the evidence
supporting the status and any unverified behavior.

## Code Structure

| File | Role |
| ---- | ---- |
| `src/<area>/<file>` | One-line description of what it owns. |

Use repository-root-relative paths. Keep the table for single-file
subsystems.

## Language and Conventions

Identify languages and applicable root toolchain/style rules. Record
local exceptions, canonical implementations to follow, and relevant
formatter, linter, type-checker, or test configuration with source
references. Distinguish enforced rules from observed patterns.

## Design and Invariants

Describe the internal decomposition, dependency direction, extension
points, and design rationale supported by code or decisions. State
invariants a change must preserve: data/state ownership, validation,
errors and recovery, compatibility, and, where relevant, concurrency,
resource lifecycle, performance budgets, and trust boundaries. Cite the
code or tests enforcing them; mark absent evidence explicitly.

## Key Types and Entry Points

List up to 10 load-bearing types, functions, commands, or entry points
with current `file:line` references. For each, give its responsibility
and caller-visible contract: inputs, outputs, side effects, and failure
behavior as applicable. Prefer symbols an agent must inspect to change
the subsystem; do not pad small modules or copy entire implementations.

## Interactions

Cross-link module docs this subsystem calls, feeds, or is called by.
Identify the API, event, schema, or shared state at each boundary, its
direction, compatibility obligations, and where integration is tested.

## How to Test

Give exact build/test/static-check commands, working directory, test
prerequisites, and observable passing evidence: expected output, exit
code, or artifact. Map behavior and invariants to owning tests; name gaps
and test-environment restrictions. Exclude deployment and operations steps.

## Review and Refactor Guide

Map likely changes to the symbols, dependent modules, and tests an agent
must inspect. State safe extension points, patterns to reuse, forbidden
coupling, and compatibility or migration checks. Record evidence-backed
improvement candidates with their benefit and success check; keep
proposals separate from current design and accepted roadmap work.

## Open Gaps / Roadmap

List coding TODOs, deferred implementation work, platform support gaps,
and implementation milestones. Tag items with `Mx` when known. Exclude
business plans, release schedules, and operational tasks.
````

## Development Loop

Coding Discipline governs writing; Review Checks govern review. This
loop connects them and defines when work is ready to release.

```text
Frame → Write → Prove → Review → Gate
          ▲          findings      │
          └────────────────────────┘
```

### The loop

**1. Frame.** Convert the request into a goal with an observable check.
Inspect the request, code, docs, and repository conventions; record the
narrowest supported assumptions. When using eatmycode, run its Version
and Freshness Gate before trusting architecture guidance. Ask one focused
question only when a required decision cannot be discovered or safely
inferred and guessing would materially change the result. Once framed,
continue without an approval pause.

**2. Write.** Make the smallest change that reaches the goal. Add no
unrequested features or abstractions, match local style, touch only
in-scope code, and remove only orphans created by the change.

**3. Prove.** Run relevant tests and retain observable evidence.

*Survey the suite before touching it.* Before adding, changing, merging,
or deleting any test, inventory the whole suite: enumerate every test
file and case name, then read in full each test whose subject, fixtures,
or assertions touch this change. Use a subagent for broad inventory when
supported. From that inventory decide the complete set of test edits at
once — what to change, what to add, what to merge, what to remove — each
backed by `file:line`, then execute only that plan. Never write a test
before the survey, and never discover existing coverage afterward.

The plan obeys four rules:

- **Reuse or extend first.** Add a case to the test that already owns
  the behavior or shares its setup, fixtures, and subject. A new test
  function or file is justified only when the survey found no existing
  test owning the behavior, or when merging would hide which case
  failed.
- **Add only what the goal needs.** A bug fix needs a reproducing
  regression test; a new capability needs a test of its claimed
  behavior. Nothing further.
- **Retire what this change made obsolete.** Delete tests whose behavior
  no longer exists, and merge tests this change turned into duplicates,
  citing the surviving test. Leave unrelated pre-existing tests alone;
  record suspected redundancy under **Open Gaps / Roadmap**.
- **Never delete to reach green.** A failing test is a finding for
  Write. Removal requires evidence that its behavior is gone or is still
  covered elsewhere, cited by `file:line`.

Coverage of claimed behavior must not decrease. A failure returns
directly to Write, never forward to Review.

**4. Review.** Walk all seven Review Checks as separate passes. Read
whole affected files, not only the diff. Every finding needs `file:line`
evidence. Use an independent agent or isolated pass for Fit,
Dependencies, and Security when available.

**5. Gate.** Apply the Definition of Done. Any unticked criterion,
`blocker`, or unresolved `major` returns its evidence to Write. All
criteria passing means the change is ready for public or production
release. There is no separate approval or reporting phase.

### Definition of Done

**Correctness**

- The framed goal and its named check pass.
- Tests cover claimed behavior and pass; a bug fix has a regression test.
- The suite was surveyed before any test was written, changed, or
  deleted; no added test duplicates coverage another test owns, and no
  removal left claimed behavior uncovered.
- The owning module's **How to Test** command passes with evidence.
- The project builds and tests from a fresh clone without local-only
  dependencies.

**Review**

- All seven Review Checks ran; none was skipped or assumed.
- No `blocker` or unresolved `major` remains.
- Nits were applied or consciously declined.

**Legibility and contract**

- An agent can locate the owning code, identify language/style/design
  constraints, select a safe change or refactor, review its impact, and
  run the right checks from `ARCHITECTURE.md` and the owning module docs.
- Every changed line serves the goal; no drive-by formatting, debugging
  remnants, commented-out code, secrets, tokens, or local paths remain.
- Public names, signatures, errors, and recovery are intelligible.
- Architecture docs and `file:line` references reflect current source;
  version stamps certify a verified contract migration, not just a
  metadata edit.
- Architecture docs contain only coding context; any encountered
  deployment guides or other non-coding material and obsolete links were
  removed from the doc set.
- Breaking changes, deprecations, dependencies, licenses, and attribution
  are handled; commit or PR text explains why.

### Iterating without thrashing

- Every pass closes a named finding and touches only what it names.
- Nits alone do not trigger another pass.
- Re-run Prove after every fix.
- Two no-change passes force Gate re-evaluation: release if Done passes;
  otherwise return the surviving evidence to Frame.
- Three passes on one finding return automatically to Frame for a new
  approach.
- Never widen scope to satisfy a finding. Record coding-related follow-up
  work under **Open Gaps / Roadmap**; keep non-coding work outside the
  architecture doc set.

## Coding Discipline

### 1. Think Before Coding

- Understand the request, code, goal, and repository conventions first.
- Record assumptions and choose the narrowest evidence-backed reading.
- Prefer the simpler approach when it reaches the same verified goal.
- Ask only during planning and only for a required answer that cannot be
  discovered or safely inferred.

### 2. Simplicity First

- Implement only what was requested.
- Do not add single-use abstractions, speculative flexibility, or checks
  for impossible conditions.
- If the implementation is materially larger than the problem, simplify
  it.

### 3. Surgical Changes

- Do not refactor, reformat, or clean up unrelated code.
- Match the surrounding style.
- Remove imports, variables, and functions made unused by this change;
  leave pre-existing dead code alone unless requested.
- Every changed line must trace to the stated goal.

### 4. Goal-Driven Execution

Turn work into verifiable outcomes, then loop until they pass:

- Add validation → invalid inputs are rejected by a named passing test.
- Fix a bug → a regression test fails before the fix and passes after.
- Refactor → behavior tests pass before and after.

Give every plan step its own check. Strengthen vague criteria from
repository evidence before implementation.

## Review Checks

Run every check against every change before merge. Keep checks separate.

Four rules bind all checks:

- **Evidence or no finding.** Every finding cites `file:line`.
- **The repository is authoritative.** Demand only conventions visible
  in the tree.
- **Read files, not only hunks.** Context can invalidate a finding or
  reveal unreachable code, unused parameters, and hidden duplication.
- **Review the change, never the author.** Describe code and impact, not
  how or by whom it was produced.

### 1. Style

Check indentation and local file conventions. Mixed indentation is
`major`; a consistent new file using the wrong local indent is `nit`.
Leave machine-checkable formatting to existing formatters and linters;
never demand unrelated reformatting.

### 2. Naming

Compare new names with nearby precedents before filing a finding. If the
repository is inconsistent, demand nothing. A local mismatch is `nit`;
an inconsistent public name is `major`.

### 3. Duplication

Search distinctive constants, errors, fields, and call sequences—not
only symbol names—for code performing the same job. Cite both sites and
the remedy. Cross-layer duplication is `major`; small local repetition
is `nit`. Similar code with meaningfully different branches is not
duplication.

### 4. Quality

Require followable control flow, errors handled where they occur, and
abstractions proportional to the problem. Swallowed errors,
inappropriate prints, unexplained magic values, and dead branches are
`major`. Remove unrequested configurability, one-caller wrappers, filler
comments, debugging remnants, and unrelated formatting. Missing tests
belong to Prove, not this check.

### 5. Fit

Read `ARCHITECTURE.md` and the owning module doc before the diff. Check
documented language/toolchain constraints, code-design conventions,
scope, layering, ownership, invariants, public-API growth, compatibility,
and performance claims against source evidence. A layering violation or
unjustified public API is `major`. Architectural or public-behavior changes
must update the relevant docs in the same change.

### 6. Dependencies

Check manifests and imports, maintenance, supply-chain risk, advisories,
install-time behavior, license, transitive cost, and whether the standard
library is sufficient. An unjustified top-level dependency is `major`;
a live advisory or abandoned upstream is `blocker`. Incomplete evidence
does not pass.

### 7. Security

Check both defects and widened exposure: unsafe memory access, unchecked
sizes or offsets, integer overflow, path traversal, unsafe
deserialization, command construction, committed secrets, and unbounded
untrusted input. Trace input to impact; without a reachable path there is
no finding. A real defect is `major`; a trust-boundary break is `blocker`.
Describe the fix without publishing exploit steps.

### Severity and the merge threshold

| Severity | Effect |
| -------- | ------ |
| `blocker` | Must not merge. |
| `major` | Must be resolved before merge. |
| `nit` | Apply or consciously decline. |
| `info` | Context or a question; no action implied. |

Merge only with no `blocker` and no unresolved `major`. A check that did
not run does not pass. Findings feed Write and Gate directly; they do not
create a reporting phase.

## Verification

After every write or fix, verify all affected behavior and structure.
A missing, unversioned, invalid, or older root requires verification of
the whole doc set. With a current root, verify the root and affected or
stale modules; retain prior verification for other current-version
modules unless changed source, shared rules, or interactions affect them.

1. The freshness gate ran for this invocation. Contents and structure
   were verified before new stamps were written; the root and all module
   versions agree with the active skill. A newer-version mismatch or
   incomplete migration is reported as pending, never certified current.
2. Every Index link resolves, every real subsystem has one owning module
   file, and paths/responsibilities/change triggers route to that owner.
3. The root contains every Root Contract section in order, followed by
   verbatim Development Loop, Coding Discipline, and Review Checks, then
   Index. Each module in verification scope uses every Module Template
   header in exact order.
4. Code paths and `file:line` references resolve to current source.
   Language/toolchain, coding-style, code-design, and architecture claims
   cite evidence; unknowns and non-applicable topics are explicit. Review
   and refactor guidance identifies constraints, owners, and checks.
   Docs in verification scope contain only coding context; excluded
   sections, non-coding-only files, and their Index entries are removed,
   and links are repaired without dropping code-relevant contracts.
5. Agent entry files managed by this workflow, when present, are symlinks
   to `ARCHITECTURE.md`; their coding guidance was migrated and useful
   non-coding guidance was preserved outside the architecture doc set.
6. Every new or updated module's **How to Test** command runs and proves
   its stated Status.
7. All seven Review Checks and the Definition of Done pass.

Any repairable miss becomes a named Coder finding. Re-run verification
after the fix, then repeat Review and Gate. If a required skill version
is unavailable or the active skill has no valid version, treat that as
an external constraint, not a Coder retry: finish independently verifiable
requested work from source, report architecture migration as pending,
and do not claim the full release gate passed. Otherwise, the task is
complete only when all checks pass and the result is ready for public or
production release. Provide the harness's normal concise completion
handoff.

## Non-Negotiables

- Inspect before planning; plan before writing; prove and review before
  Gate.
- Run the version/freshness check on every use; never certify stale or
  partially migrated architecture with a new version stamp.
- Write architecture docs for agent decisions and navigation; keep
  evidence-backed rules distinct from observations and proposals.
- Remove non-coding content encountered in architecture docs; never
  import deployment or operations guides into them.
- Preserve agent-file guidance in the appropriate docs before replacing
  regular files; architecture receives coding guidance only.
- Keep module prose in one owning module file and links and line
  references current.
- Never mark `done` without a passing **How to Test** command.
- Never delete or weaken a test to turn a red run green.
- Tester and Verifier never repair their own findings.
- Resolve unknowns from evidence or the single planning-question
  exception; otherwise state the missing evidence and its impact on the
  task. Never present guesses or unfilled template text as project facts.
