# codereview

## Mission

Review GitHub pull requests and answer issues using the target project's
architecture and source. A specialist panel investigates, challenges its own
conclusions, and produces one evidence-backed report for a maintainer.
PR reviewers each cast a merge recommendation; the tool never merges.

Every repository is treated equally. `--repo` is required. The target's source
and architecture are authoritative; optional repository profiles supplement
them. No project-specific profile ships.

## Target environment

Linux or macOS, Python 3.10+, `git`, authenticated `gh`, and an OpenAI-compatible
model endpoint. Installing the pinned kerness Rust extension also needs a Rust
toolchain and a C linker. See [README.md](README.md) for setup and invocation.

The sole Python dependency is kerness, built using the README commands from public revision
`7c97dcb4e50a8fd05d05185b0052ba1356be016a` with the tracked PyO3 compatibility
and security patch. `requirements.txt` records the installed package version.
Runtime uses its strict session API. `vendor/kerness/` is an optional development
checkout, not a required local-only dependency. The eatmycode specification is
fetched from upstream on every invocation; offline or unsupported specification
changes stop preflight.

## Workspace layout

| Path | Ownership |
| ---- | --------- |
| `code.sh`, `review.py` | Launcher and workflow coordination |
| `patches/` | Upstream compatibility patch and dependency build provenance |
| `architecture.py` | Latest eatmycode specification and architecture preparation |
| `panel_runtime.py`, `session_builder.py` | Session contracts, participation, ballots and progress |
| `reporting.py` | Report validation, approval gate and Markdown rendering |
| `repo_facts.py`, `agent_tools.py` | Measured facts and read-only panel tools |
| `git_io.py`, `github_io.py` | Managed checkouts and GitHub CLI boundary |
| `gameplans/`, `personas/`, `prompts/` | Panel phases, specialist roles, optional review knowledge |
| `tests/` | Offline behavioral and integration checks |
| `repo/` | Ignored managed clones and retained `.reviews/` worktrees |
| `vendor/` | Ignored upstream specification and optional kerness checkout |

`AGENT.md`, `AGENTS.md` and `CLAUDE.md` point here. The module Index owns subsystem details;
keep those details out of this control center.

## Entry flow

1. `code.sh` selects `.venv/bin/python` (or legacy `venv/bin/python`) and forwards
   arguments to `review.py` without changing the caller's working directory or
   processing its output. `review.py` parses `--id NUMBER` for automatic routing;
   legacy positional `auto|pr|issue NUMBER` remains supported.
2. Validate credentials/options, refresh eatmycode, and prepare documentation
   against the configured/default branch before identifying the target kind.
3. Confirm whether the number is a PR or issue. `--id` routes it; an incorrect
   explicit `pr` or `issue` exits with the actual kind.
4. A PR gets a fresh review branch, an immutable source worktree and a second
   documentation audit of its own head. An issue uses the baseline source and
   audited documentation. Generated guides occupy separate local worktrees;
   original source remains the citation authority.
5. Run the appropriate panel. Every specialist studies architecture, owning
   module documents and complete related source before reaching conclusions.
6. Check actual participation, strict result fields, citations and ballots.
   Print one report; post through `gh` unless `--dry-run`. A PR changing during
   review invalidates the result before posting.

The PR panel has language/tooling, API design, refactoring, senior engineering,
architecture, supply-chain and security specialists. Each participates in
study, review, debate, verification and voting. The chair records its own
vote after hearing everyone. Approval requires all eight merge votes, seven
passing checks, justified need, no major/blocker findings, an open non-draft
PR and an approving rubric verdict. `--allow-approve` additionally controls
whether GitHub receives an approval or a comment.

## Hard guardrails

- All GitHub service access goes through `github_io.gh`; target/specification
  git transport goes through `git_io.git`. No raw GitHub API writes.
- Never merge, close a PR/issue, push, or apply labels. Known command forms are
  denied centrally; available writes are PR reviews and issue comments only.
- Never execute target tests, builds or scripts. Panel gameplans expose no
  command, shell, write or memory-write tool. Local project-development tests
  are distinct from reviewing an untrusted target.
- Panel file access is confined to its source checkout, explicitly allowed
  generated guide files and an optional caller-selected transcript path.
- Generated documentation is applied only to retained local worktrees after
  validation, with rollback on write failure. It is never pushed or committed.
- Preserve dirty managed clones and existing durable agent guidance. Do not
  reset uncommitted work or silently replace a different repository's clone.
- Hold API credentials in memory. Disable kerness session persistence and
  never include credentials in topics, reports or transcripts.
- Incomplete evidence does not pass. Missing reviewers, malformed results,
  rejected documentation audits and invalid citations stop publication.

## Roadmap

- **M1 — Documentation-first routing:** latest specification, safe local doc
  preparation, separate original source and guide, PR/issue identification.
- **M2 — Accountable review:** distinct specialists, debate, attributed votes,
  strict completion and approval gates, readable reports.
- **M3 — Public project quality:** reproducible installation, direct launcher,
  offline integration tests, current architecture and independent review.

M1–M3 are implemented. The automated checks exercise scripted model replies;
live model quality and GitHub posting require a separately configured smoke
run. See the module gaps for operational limitations.

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
narrowest supported assumptions. Ask one focused question only when a
required decision cannot be discovered or safely inferred and guessing
would materially change the result. Once framed, continue without an
approval pause.

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

- A new maintainer can build, test, run, and understand public behavior
  from the docs.
- Every changed line serves the goal; no drive-by formatting, debugging
  remnants, commented-out code, secrets, tokens, or local paths remain.
- Public names, signatures, errors, and recovery are intelligible.
- Architecture docs and `file:line` references are current.
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
- Never widen scope to satisfy a finding. Record out-of-scope work under
  **Open Gaps / Roadmap**.

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
scope, layering, ownership, public-API growth, and performance claims. A
layering violation or unjustified public API is `major`. Architectural or
public-behavior changes must update the relevant docs in the same change.

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
- The generic review rubric requires a demonstrated need before approval.
  Preserve `Need: justified`, `Need: unclear` or `Need: unnecessary` in Fit's
  checklist note. Missing context is a concern, not a fabricated code defect.
- A second top-level dependency needs evidence that the standard library
  cannot reasonably implement the required behavior.

## Index

- [Workflow and launcher](ARCHITECTURE/review-cli.md)
- [Architecture preflight](ARCHITECTURE/architecture-preflight.md)
- [Panels, tools and attributed ballots](ARCHITECTURE/harness.md)
- [Report and approval policy](ARCHITECTURE/reporting.md)
- [GitHub access](ARCHITECTURE/github-io.md)
- [Git checkouts](ARCHITECTURE/git-io.md)
- [Repository profiles and prompts](ARCHITECTURE/prompts.md)
