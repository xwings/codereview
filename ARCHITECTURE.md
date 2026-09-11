---
eatmycode_version: "1.2.0"
---
# codereview

## Mission and Constraints

Review GitHub pull requests and answer issues using the target project's
architecture and source. A lead reviewer investigates and an independent
verifier checks every PR; issue verification runs for uncertain or substantial
conclusions. The host produces one evidence-backed report for a maintainer.
PRs merge only into isolated local review sources; the tool never merges a PR on GitHub.

Every repository is treated equally: `--repo` and `--branch` are required,
the selected source snapshot is authoritative, and optional profiles only
supplement it. No project-specific profile ships (`review.py:77`, `review.py:158`).
Linux and macOS with Python 3.10+ and Git 2.32+ are declared supported in
`README.md:10`. Target tests, builds and scripts are never executed; this tool's
own development tests are separate. Preflight fetches the latest eatmycode
specification on every run; unavailable or malformed upstream rules stop the
run. Release numbers and a remembered contract fingerprint do not select the rules.

## Languages and Toolchain

| Area | Declared toolchain and evidence |
| ---- | ------------------------------- |
| Root Python modules and `tests/` | Python 3.10+; standard library plus kerness (`README.md:10`, `requirements.txt:4`) |
| `code.sh` | Bash with strict error handling and direct `exec` (`code.sh:1`) |
| `gameplans/`, `personas/`, `prompts/` | Markdown profiles and YAML gameplan frontmatter interpreted by Python/kerness |
| Dependency binding | Rust toolchain, C linker, Cargo and maturin build backend through pip; pinned public source and PyO3 patch (`patches/README.md:3`) |
| Git transport and GitHub service | Git 2.32+ and authenticated `gh`; argv-based boundaries (`git_io.py:24`, `github_io.py:48`) |

Kerness is the sole Python dependency, installed from public revision
`7c97dcb4e50a8fd05d05185b0052ba1356be016a` with the tracked compatibility and
security patch. `requirements.txt` records its installed version; it is not a
PyPI bootstrap. The optional ignored `vendor/kerness/` source checkout is not a
runtime dependency. No project-level CI, formatter, linter or type-checker
configuration is tracked; locally installed tool versions do not define support.

## System Design

`review.py` coordinates the workflow. `progress.py` supplies shared stderr
messages with local timestamp, model, agent and phase, plus elapsed-time
heartbeats for the CLI and panel runtime.
The CLI calls architecture preparation, checkout/GitHub boundaries, panel
construction/runtime, and report validation;
those modules own their contracts and do not import the CLI. `repo_facts.py`
and `agent_tools.py` collect inspection evidence through the I/O boundaries.
Gameplans and personas define review contracts and expertise. Host code selects
Lead, any requested Security/Dependencies consultants, then Verifier. All seven
checks remain separate. It validates authenticated turns, result shape and
independent assessments (`panel_runtime.py:169`).
`provider_io.py` observes actual HTTP attempts and assembled request sizes while
leaving retries and compatibility fallbacks to kerness.
The [Index](#index) routes subsystem changes and their interaction partners.

Cross-cutting invariants:

- All GitHub service access goes through `github_io.gh`; target/specification
  git transport goes through `git_io.git`. No raw GitHub API writes.
- Never merge a PR on GitHub, close a PR/issue, push, or apply labels. Known
  command forms are denied centrally; available service writes are PR reviews
  and issue comments only. PR source preparation permits an isolated local merge.
- Never execute target tests, builds or scripts. Panel gameplans expose no
  command, shell, write or memory-write tool.
- Panel reads stay inside its source checkout, explicitly allowed generated
  guide files and an optional caller-selected transcript (`session_builder.py:39`).
- Generated documentation is validated before writes to retained local guide
  worktrees, with rollback on write failure. It is never pushed or committed.
- Preserve managed working trees, local branch refs and durable agent guidance.
  Reject dirty clones; do not reset work or replace a different repository's clone
  (`git_io.py:62`, `git_io.py:83`).
- Keep credentials in memory; disable kerness session persistence and exclude
  credentials from topics, reports and transcripts (`session_builder.py:28`).
- Missing reviewers, malformed results, rejected documentation audits and invalid
  citations stop publication (`panel_runtime.py:169`, `reporting.py:41`).

## Runtime and Data Flow

1. `code.sh` selects `.venv/bin/python` or legacy `venv/bin/python`, forwards
   arguments and preserves the caller's directory and process exit status.
   `review.py:77` accepts `--id NUMBER` or legacy `auto|pr|issue NUMBER`.
2. `review.py:430` validates options and credentials, identifies the PR/issue
   kind and rejects an explicit mismatch before source preparation. It fetches
   PR metadata when applicable, then checks the managed clone.
3. Git prepares an isolated snapshot of the required `--branch`. Issues use
   that branch exactly; PRs merge the pinned PR head into it locally. Conflicts
   and changed fetched heads stop before documentation or model calls. The CLI
   refreshes eatmycode and checks `ARCHITECTURE.md` plus every Markdown file
   recursively under `ARCHITECTURE/`, including supporting pages. Matching
   versions and sizes at most 35,000 Unicode characters skip documentation
   preparation. Missing, invalid, older or oversized docs receive a local update
   in a separate retained guide worktree; newer docs are preserved without
   downgrading (`git_io.py:109`, `review.py:315`).
4. Lead reviews architecture and complete relevant source, optional consultants
   investigate focused questions, and Verifier accounts for every finding. Issues
   use one investigation and conditional verification. A missing or malformed
   result record permits one format-correction turn by the same reviewer;
   both attempts remain in authenticated history. Complete JSON with ordinary
   indentation, line breaks or fences is accepted
   without correction in both verbosity modes (see [panels](ARCHITECTURE/harness.md)).
   Invalid schemas or citations still stop the run. The host validates
   participation, result fields, citations and assessments, then renders one report
   naming the selected branch, pinned base and reviewed revision. PR reports close
   with an explicit merge instruction and the approval reason or unmet requirements.
   PR citations refer to the local merge
   result and may differ from GitHub PR-head lines.
5. `review.py:347` prints Markdown to stdout and posts through `gh` unless
   `--dry-run`. PR metadata is checked again before publication. Progress and
   suggested labels go to stderr; errors and interruption return nonzero.
   The complete workflow runs without `--verbose` or a transcript; `--verbose`
   adds the panel discussion to stderr.

CLI flags and `REVIEW_API_KEY`, `REVIEW_API_BASE`, `REVIEW_MODEL` configure the
provider. Model retry sequences allow two retries with 30-second pauses;
`--timeout` limits each attempt. `--panel-timeout` defaults to a cooperative
900-second budget shared by each panel's agents, tools, retries and fallbacks.
It is checked between actions; active HTTP calls and remaining retry pauses can
overrun it. Late results are rejected. There is no whole-CLI deadline
(see [provider retries](ARCHITECTURE/harness.md#design-and-invariants)).
The CLI uses the OS default SIGINT action so Ctrl+C immediately terminates native
calls too (`review.py:470`); imported library calls retain the caller's handling.
Each active progress scope schedules a heartbeat every 15 seconds. Its temporary
thread is stopped and joined on normal or exceptional scope exit (`progress.py:22`);
OS termination bypasses Python cleanup. Panel status identifies logical request counts,
model waits, evidence inspection and completed review turns using
`[YYYY-MM-DD HH:MM:SS] [model] [agent] [phase]`. Documentation phases follow
the required specialist rotation; provider purpose identifies summary calls.
Verbose mode adds agent and system exchanges; default output excludes them.
Actual HTTP attempts label initial sends, retries and compatibility fallbacks.
Each POST logs serialized prompt/payload sizes and a characters/4 token estimate;
provider-reported input tokens appear separately. Measurements exclude contents
and credentials and do not establish timeout cause (see [panels](ARCHITECTURE/harness.md)).
Heartbeats include activity elapsed time and total step/panel duration.
Optional transcripts are explicit files; session state is not persisted.
Managed clones, isolated source repositories, guide worktrees and the upstream
rule cache are retained across process exit. There is no service, database or
shutdown worker. See [workflow](ARCHITECTURE/review-cli.md) and
[panels](ARCHITECTURE/harness.md) for contracts and failure paths.

## Workspace Map

| Path | Ownership and edit constraints |
| ---- | ------------------------------ |
| `code.sh`, `review.py`, `progress.py`, `repo_facts.py` | Launcher, coordination, stderr activity/heartbeat and measured PR leads |
| `architecture.py` | Specification refresh, audit and validated local documentation writes |
| `panel_runtime.py`, `session_builder.py`, `provider_io.py`, `agent_tools.py` | Panel execution, request observations, access policy and read-only tools |
| `reporting.py` | Result validation and Markdown rendering |
| `git_io.py`, `github_io.py` | Git transport, managed snapshots and GitHub CLI boundary |
| `gameplans/`, `personas/`, `prompts/` | Panel contracts, specialist roles and optional review knowledge |
| `tests/` | Offline behavioral/integration checks using temporary repositories and scripted replies |
| `patches/`, `requirements.txt` | Dependency patch/provenance and installed version; regenerate only with a verified public revision |
| `ARCHITECTURE.md`, `ARCHITECTURE/` | Coding reference; `AGENT.md`, `AGENTS.md`, `CLAUDE.md` symlink to the root |
| `repo/` | Ignored managed target clones and retained `.reviews/` sources/guides; never treat as tool source |
| `vendor/` | Ignored specification cache refreshed by preflight and optional dependency checkout built below |

## Coding Style and Code Design

Observed Python conventions are four-space indentation, `snake_case` functions,
`UPPER_CASE` constants, standard-library imports before local imports, postponed
annotations and typed boundaries. Reuse `Path`, dataclasses for fixed internal
records, and dictionaries for model/CLI payloads (`panel_runtime.py:84`,
`session_builder.py:39`, `reporting.py:226`). Annotations are not uniform or
statically enforced; preserve the surrounding style rather than imposing a new
checker. No formatter/linter/type-check command is configured.

Keep external commands argv-based and inside their I/O owner. Validation modules
raise domain errors; CLI coordination turns them into concise nonzero exits.
Tool handlers return explicit unavailable-evidence text so the panel can record
a gap (`agent_tools.py:101`). Runtime progress is flushed to stderr; stdout
belongs to the final report. Tests use `unittest`, temporary directories, mocks and scripted
kerness providers (`tests/test_workflow.py:52`). Add no top-level dependency
without evidence that standard-library implementation is unreasonable.

## Verification and Review Map

Run from the repository root. Initial developer setup requires Python 3.10+,
Rust, a C linker and Git 2.32+; the pinned dependency can be built from public source:

```sh
python3 -m venv .venv
git clone https://github.com/xwings/kerness.git vendor/kerness
git -C vendor/kerness checkout --detach 7c97dcb4e50a8fd05d05185b0052ba1356be016a
git -C vendor/kerness apply ../../patches/kerness-pyo3.patch
MATURIN_PEP517_ARGS='--locked' .venv/bin/pip install ./vendor/kerness/bindings/python
.venv/bin/python -m kerness.selfcheck
```

With the dependency installed, run the offline suite and static syntax checks:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q *.py tests
bash -n code.sh
./code.sh --help
```

Expected evidence: `OK` from unittest, successful kerness selfcheck, no compile
or Bash diagnostics, and help listing the documented options; every command
exits zero. There is no separate application build step or configured CI,
lint/type-check target. Dependency patch changes additionally use the optional
upstream checks in [harness](ARCHITECTURE/harness.md).

| Change owner | Required verification and limits |
| ------------ | -------------------------------- |
| Architecture preflight | `tests/test_architecture.py`: temporary upstream refresh/update/failure, version gates, current-doc reuse, full proposal validation, preservation and rollback; owning doc also gives the live upstream compatibility check |
| CLI, Git/GitHub and profiles | `tests/test_workflow.py`, `tests/test_git_io.py`: required branch/routing, isolated local merges, source citations, body-file writes and no-write guards |
| Panels and reporting | `tests/test_workflow.py`: real scripted review sequences, independent assessments/audits, strict completion, approval and rendering |
| Documentation | Validate source references, links/anchors, exact shared/root/module sections, supporting-page ownership, matching verified stamps and each file's 35,000-character limit |

Offline tests use no external model calls or GitHub writes and never execute
untrusted target code. Live model interpretation and GitHub posting remain
unverified by that suite. Fresh-clone builds must use the public pin and tracked
patch, with no local-only dependency. Target review claims remain limited to
source and supplied evidence.

## Roadmap

- **M1 — Documentation-first routing:** implemented latest-specification
  preparation after PR/issue detection, selected-branch source and local PR
  merges, with generated guides kept separate.
  The architecture owner maintains versioned contracts and migration checks.
- **M2 — Accountable review:** implemented bounded review and independent verification, attributed assessments,
  strict completion/approval gates and readable reports.
- **M3 — Public project quality:** implemented reproducible dependency setup,
  direct launcher and offline integration tests; architecture is audited against
  source. Live provider quality and posting are not proved by scripted replies.

No additional milestones are accepted. Evidence-backed candidates are recorded
in owning module gaps: bounded overall execution and broader measurement
coverage in workflow, concurrent workspace and specification-cache access, and non-PyPI
advisory coverage in panels. Each requires explicit scope and behavioral
verification before it becomes accepted work.

## Development Loop

Frame → Write → Prove → Review → Gate. Findings return to Write;
uncertainty that changes the plan returns to Frame.

Use one subagent per role when available, otherwise distinct labeled
passes. Tester and Verifier report findings and never edit; Coder repairs.

| Role | Stages | Handoff |
| ---- | ------ | ------- |
| Planner | Frame | Goal, observable checks, assumptions, affected files/owners, and plan. |
| Coder | Write | Planned changes or repairs to named findings. |
| Tester | Prove | Commands, results, and behavioral/structural evidence. |
| Verifier | Review + Gate | Evidence-backed findings or verified completion. |

### The loop

1. **Frame:** Inspect the request, code, docs, and conventions before
   planning. Give the goal and each plan step an observable check. When
   using eatmycode, run its Version and Freshness Gate before trusting
   architecture; include versions, migration scope, Index/agent-file
   changes, and verification commands in architecture plans. Resolve
   uncertainty from evidence and record the narrowest supported assumptions.
   Only Planner may ask one focused question, when a required decision
   cannot be discovered or safely inferred and guessing changes the result.
2. **Write:** Apply Coding Discipline. Make the planned change; for a
   repair, address only named findings. Update affected architecture with
   changes to its documented contracts.
3. **Prove:** Run relevant tests and structural checks, retaining observable
   evidence. For architecture work under eatmycode, apply its Architecture
   Verification. Failures and missing, duplicate, or obsolete coverage
   become Coder findings. Re-run affected checks after repairs; never send
   a red result to Review.
4. **Review:** Apply every Review Check as a separate pass over full affected
   files. Use an independent agent or isolated pass for Fit, Dependencies,
   and Security when available. Return findings to Coder, then re-prove
   and re-review the repairs.
5. **Gate:** Confirm completion only when the Definition of Done passes.
   Return unmet criteria to the responsible stage; continue until resolved.
   If an external constraint prevents verification, state the missing
   evidence and remaining work without claiming completion or readiness.

Handoffs are automatic. Continue without pauses for plan approval,
permission to continue, or review/reporting ceremonies. Finish with the
harness's normal concise completion handoff.

### Definition of Done

- **Correctness:** The goal and named checks pass. Tests cover claimed
  behavior; bug fixes have a reproducing regression test. The project
  builds and tests from a fresh clone without local-only dependencies.
  Owning modules' **How to Test** commands pass with evidence.
- **Review:** Every Review Check ran and its completion threshold passes.
- **Contract:** Docs reflect source and let an agent locate owners,
  constraints, and verification commands. When using eatmycode, architecture
  satisfies its Output Contract, verification, and version rules. Public
  names, signatures, errors, and recovery are intelligible. Breaking
  changes, deprecations, dependencies, licenses, and attribution are handled;
  commit or PR text, when present, explains why.
- **Scope:** Changed lines serve the goal and follow Coding Discipline;
  no debugging remnants, commented-out code, secrets, tokens, or local paths
  remain. Test edits follow the inventory and coverage rules below.

### Iterating without thrashing

- Each repair pass targets a named finding; nits alone do not trigger one.
- Two no-change passes force Gate re-evaluation. If Done still fails,
  return the surviving evidence to Frame.
- Three passes against the same finding return to Frame for a new approach.
- Never widen scope to satisfy a finding. Record coding follow-ups under
  **Open Gaps / Roadmap** and keep non-coding work outside architecture.

## Coding Discipline

- Implement only the goal. Prefer the simplest approach that passes its
  checks; simplify code materially larger than the problem.
- Match local style. Avoid speculative features, flexibility, single-use
  abstractions, and checks for impossible conditions.
- Keep edits surgical: no unrelated refactoring, reformatting, or cleanup.
  Remove imports, variables, and functions made unused by this change;
  leave pre-existing dead code alone unless requested.
- Make success concrete: validation rejects invalid input in a named test;
  a regression test fails before a bug fix and passes after; behavior tests
  pass before and after a refactor.

### Before editing tests

Before any test edit, including during Write, inventory the whole suite:
enumerate every test file and case name, then read in full tests whose
subject, fixtures, or assertions touch the change. Use a subagent for broad
inventory when supported. Plan all additions, changes, merges, and removals
from that evidence, citing `file:line`, before executing the test edits.

- **Reuse first:** Extend the test owning the behavior or sharing its
  setup, fixtures, and subject. Add a function/file only if no existing
  owner fits or merging would obscure which case failed.
- **Add only required coverage:** A bug fix needs its regression test;
  a capability needs a test of its claimed behavior. Avoid duplicates.
- **Retire only what changed:** Remove tests of deleted behavior and merge
  new duplicates, citing surviving coverage. Record unrelated suspected
  redundancy under **Open Gaps / Roadmap**.
- **Preserve coverage:** Never delete or weaken tests to turn red green.
  Removal needs evidence that behavior is gone or covered elsewhere;
  coverage of claimed behavior must not decrease.

## Review Checks

Run every check against every change before confirming a code edit is
complete, even when no commit or merge is requested. Keep checks separate.

- **Evidence or no finding:** Cite `file:line` for every finding.
- **Repository authority:** Demand only conventions supported by the tree.
- **Full context:** Read affected files, not only hunks; context can expose
  unreachable code, unused parameters, or hidden duplication.
- **Code and impact:** Review the change, never the author or how it was made.

### 1. Style and Naming

Check indentation and local conventions; leave machine-checkable formatting
to existing formatters/linters and never demand unrelated reformatting.
Mixed indentation is `major`; a consistent new file with the wrong local
indent is `nit`. Compare names with nearby precedents. If the repository
is inconsistent, demand nothing. A local naming mismatch is `nit`; an
inconsistent public name is `major`.

### 2. Duplication

Search distinctive constants, errors, fields, and call sequences, beyond
symbol names, for the same job. Cite both sites and a remedy. Cross-layer
duplication is `major`; small local repetition is `nit`. Similar code with
meaningfully different branches is not duplication.

### 3. Quality

Require followable control flow, errors handled where they occur, and
proportionate abstractions. Swallowed errors, inappropriate prints,
unexplained magic values, and dead branches are `major`. Remove unrequested
configurability, one-caller wrappers, filler comments, debugging remnants,
and unrelated formatting. Missing tests belong to Prove.

### 4. Fit

Read the root architecture and owning module before the diff. Check
language/toolchain constraints, conventions, scope, layering, ownership,
invariants, public-API growth, compatibility, and performance claims against
source. A layering violation or unjustified public API is `major`.
Architectural/public-behavior changes need matching docs in the same change.

### 5. Dependencies

Check manifests/imports, maintenance, supply-chain risk, advisories,
install-time behavior, license, transitive cost, and standard-library
alternatives. An unjustified top-level dependency is `major`; a live
advisory or abandoned upstream is `blocker`. Incomplete evidence does not pass.

### 6. Security

Check defects and widened exposure: unsafe memory access, unchecked sizes
or offsets, integer overflow, traversal, unsafe deserialization, command
construction, committed secrets, and unbounded untrusted input. Trace input
to impact; without a reachable path there is no finding. A real defect is
`major`; a trust-boundary break is `blocker`. Describe fixes without exploit
steps.

### Severity and the completion threshold

| Severity | Effect |
| -------- | ------ |
| `blocker` | Must not confirm completion or merge. |
| `major` | Must be resolved before confirming completion or merging. |
| `nit` | Apply or consciously decline. |
| `info` | Context or a question; no action implied. |

Confirm completion or merge only with no `blocker` or unresolved `major`.
A check that did not run does not pass; explain evidence-backed
inapplicability. Findings feed Write and Gate directly.

### Project-Specific Deviations

- The shared development checks govern changes to this tool. Reviews of target
  submissions inspect source and documentation only; they never claim a target
  test run or full eatmycode release compliance. This does not waive this
  project's own build, test or review criteria.
- The review product retains seven separate checklist keys, including Style
  and Naming, as enforced by `reporting.py:9`. The shared development rubric
  groups those topics in one check without changing the review result schema.
- Target preflight checks every architecture Markdown version and file size.
  Matching docs skip the documentation source audit; the review panel still
  inspects relevant source and the context discloses the skipped checks. See
  [preflight](ARCHITECTURE/architecture-preflight.md).
- The generic review rubric requires a demonstrated need before approval.
  Preserve `Need: justified`, `Need: unclear` or `Need: unnecessary` in Fit's
  checklist note. Missing context is a concern, not a fabricated code defect.
- A second top-level dependency needs evidence that the standard library
  cannot reasonably implement the required behavior.

## Index

| Owning module | Source paths | Responsibility and change triggers |
| ------------- | ------------ | ---------------------------------- |
| [Workflow and launcher](ARCHITECTURE/review-cli.md) | `review.py`, `code.sh`, `progress.py`, `repo_facts.py` | Routing, configuration, source/guide flow, shared progress and measured PR leads; read I/O, preflight and panel partners when changing coordination |
| [Architecture preflight](ARCHITECTURE/architecture-preflight.md) | `architecture.py`, `gameplans/architecture_docs.md`, `personas/docs_*.md` | Upstream contract, freshness, source audit, document validation/migration and local writes; consult panel and Git contracts |
| [Reviews, tools and verification](ARCHITECTURE/harness.md) | `panel_runtime.py`, `session_builder.py`, `provider_io.py`, `agent_tools.py`, `gameplans/`, `personas/`, `patches/`, `requirements.txt` | Runtime, rosters, read boundaries, request/progress observations, strict completion and dependency integration; PR/issue gameplans and non-doc personas owned here; docs behavior belongs to preflight |
| [Report and approval policy](ARCHITECTURE/reporting.md) | `reporting.py` | Result/citation validation, approval eligibility and rendering; assessment changes also require runtime/CLI review |
| [GitHub access](ARCHITECTURE/github-io.md) | `github_io.py` | Service reads, kind detection, permitted report writes and shared command restrictions; inspect Git/CLI callers |
| [Git checkouts](ARCHITECTURE/git-io.md) | `git_io.py` | Origins, clean clones, isolated branch/merge sources, pinned diffs and guide worktrees; consult preflight/CLI source ownership |
| [Profiles and prompts](ARCHITECTURE/prompts.md) | `prompts/`, profile/topic functions in `review.py` | Supplementary Markdown knowledge and review rubric; source authority and report gates constrain changes |
