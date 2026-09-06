---
eatmycode_version: "1.1.0"
---
# codereview

## Mission and Constraints

Review GitHub pull requests and answer issues using the target project's
architecture and source. A specialist panel investigates, challenges its own
conclusions, and produces one evidence-backed report for a maintainer. PR
reviewers each cast a merge recommendation. PRs merge only into isolated local
review sources; the tool never merges a PR on GitHub.

Every repository is treated equally: `--repo` and `--branch` are required,
the selected source snapshot is authoritative, and optional profiles only
supplement it. No project-specific profile ships (`review.py:76`, `review.py:153`).
Linux and macOS with Python 3.10+ and Git 2.32+ are declared supported in
`README.md:10`. Target tests, builds and scripts are never executed; this tool's
own development tests are separate. Offline or unsupported eatmycode
specification changes stop preflight.

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
activity messages and elapsed-time heartbeats to the CLI and panel runtime.
The CLI calls architecture preparation, checkout/GitHub boundaries, panel
construction/runtime, and report validation;
those modules own their contracts and do not import the CLI. `repo_facts.py`
and `agent_tools.py` collect inspection evidence through the I/O boundaries.
Gameplans and personas define panel behavior; host code verifies actual
participation, result shape and independent ballots (`panel_runtime.py:141`).
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
  guide files and an optional caller-selected transcript (`session_builder.py:38`).
- Generated documentation is validated before writes to retained local guide
  worktrees, with rollback on write failure. It is never pushed or committed.
- Preserve managed working trees, local branch refs and durable agent guidance.
  Reject dirty clones; do not reset work or replace a different repository's clone
  (`git_io.py:62`, `git_io.py:83`).
- Keep credentials in memory; disable kerness session persistence and exclude
  credentials from topics, reports and transcripts (`session_builder.py:29`).
- Missing reviewers, malformed results, rejected documentation audits and invalid
  citations stop publication (`panel_runtime.py:141`, `reporting.py:41`).

## Runtime and Data Flow

1. `code.sh` selects `.venv/bin/python` or legacy `venv/bin/python`, forwards
   arguments and preserves the caller's directory and process exit status.
   `review.py:76` accepts `--id NUMBER` or legacy `auto|pr|issue NUMBER`.
2. `review.py:419` validates options and credentials, identifies the PR/issue
   kind and rejects an explicit mismatch before source preparation. It fetches
   PR metadata when applicable, then checks the managed clone.
3. Git prepares an isolated snapshot of the required `--branch`. Issues use
   that branch exactly; PRs merge the pinned PR head into it locally. Conflicts
   and changed fetched heads stop before documentation or model calls. The CLI
   refreshes eatmycode and checks the final source's root version once. A current
   `ARCHITECTURE.md` skips documentation preparation; missing or outdated roots
   receive a separate retained guide worktree (`git_io.py:109`, `review.py:310`).
4. The panel studies architecture and complete relevant source, debates findings
   and verifies conclusions. The host checks participation, strict result fields,
   citations and ballots, then renders one report naming the selected branch,
   pinned base and reviewed revision. PR citations refer to the local merge
   result and may differ from GitHub PR-head lines.
5. `review.py:340` prints Markdown to stdout and posts through `gh` unless
   `--dry-run`. PR metadata is checked again before publication. Progress and
   suggested labels go to stderr; errors and interruption return nonzero.

CLI flags and `REVIEW_API_KEY`, `REVIEW_API_BASE`, `REVIEW_MODEL` configure the
provider. `--timeout` limits each model request; calls are synchronous, with no
whole-run deadline. Each active progress scope has a temporary thread that
prints a heartbeat every 15 seconds and is stopped and joined on scope exit,
including errors and interruption (`progress.py:15`). Panel status identifies
model waits, evidence inspection, phases and completed specialist turns.
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
| `panel_runtime.py`, `session_builder.py`, `agent_tools.py` | Panel execution, access policy and read-only tools |
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
records, and dictionaries for model/CLI payloads (`panel_runtime.py:102`,
`session_builder.py:38`, `reporting.py:57`). Annotations are not uniform or
statically enforced; preserve the surrounding style rather than imposing a new
checker. No formatter/linter/type-check command is configured.

Keep external commands argv-based and inside their I/O owner. Validation modules
raise domain errors; CLI coordination turns them into concise nonzero exits.
Tool handlers return explicit unavailable-evidence text so the panel can record
a gap (`agent_tools.py:101`). Runtime progress is flushed to stderr; stdout
belongs to the final report. Tests use `unittest`, temporary directories, mocks and scripted
kerness providers (`tests/test_workflow.py:38`). Add no top-level dependency
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
| Panels and reporting | `tests/test_workflow.py`: real scripted session rounds, independent ballots/audits, strict completion, approval and rendering |
| Documentation | Validate current source references, relative links, exact shared/root/module sections and matching verified version stamps |

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
- **M2 — Accountable review:** implemented specialist debate, attributed votes,
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

### Project-Specific Deviations

- The shared release checks govern development of this tool. Reviews of target
  submissions inspect source and documentation only; they never claim a target
  test run or full eatmycode release compliance. This does not waive this
  project's own build, test or review criteria.
- Target documentation preparation checks only the root `ARCHITECTURE.md`
  version. A matching version skips preparation without checking modules,
  structure, references or agent guidance. The context discloses the skipped
  checks; review panels still inspect relevant source. See
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
| [Panels, tools and ballots](ARCHITECTURE/harness.md) | `panel_runtime.py`, `session_builder.py`, `agent_tools.py`, `gameplans/`, `personas/`, `patches/`, `requirements.txt` | Runtime, rosters, read boundaries, progress, strict completion and dependency integration; PR/issue gameplans and non-doc personas owned here; docs behavior belongs to preflight |
| [Report and approval policy](ARCHITECTURE/reporting.md) | `reporting.py` | Result/citation validation, approval eligibility and rendering; ballot changes also require panel/CLI review |
| [GitHub access](ARCHITECTURE/github-io.md) | `github_io.py` | Service reads, kind detection, permitted report writes and shared command restrictions; inspect Git/CLI callers |
| [Git checkouts](ARCHITECTURE/git-io.md) | `git_io.py` | Origins, clean clones, isolated branch/merge sources, pinned diffs and guide worktrees; consult preflight/CLI source ownership |
| [Profiles and prompts](ARCHITECTURE/prompts.md) | `prompts/`, profile/topic functions in `review.py` | Supplementary Markdown knowledge and review rubric; source authority and report gates constrain changes |
