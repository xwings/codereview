# `review.py` — PR/Issue Review Tool

## Purpose

A maintainer-facing CLI that hands a PR or issue from any GitHub repository to
a panel of LLM reviewers for a code-quality and design-fit review, then posts
the verdict back to GitHub. It augments — never replaces — maintainer judgment.

`--repo` says which repository, and is required — the tool has no home project
and plays no favourites. What the panel knows about a given project lives in
`prompts/repos/<owner>/<name>/`, so onboarding a repo is a directory, not a code
change; a repo without one is reviewed against the generic rubric in
`prompts/default/`, which is a real review rather than a degraded one. No
profile ships. See [Repo profiles](#repo-profiles).

The panel is seven specialists plus a chair, one specialist per check the
maintainer cares about:

| # | Check | Seat |
| - | ----- | ---- |
| 1 | Coding style per language (Python 4 spaces, C tabs, …) | Style |
| 2 | Naming conventions taken from the project itself | Naming |
| 3 | Near-duplicate functions — merge or refactor instead? | Duplication |
| 4 | Code quality; dead code, filler AI-generated comments | Quality |
| 5 | Does this fit the project, and make it better rather than worse? | Fit |
| 6 | New packages: maintained? supply-chain exposure? worth it? | Dependencies |
| 7 | Security bugs; does it make the project more vulnerable? | Security |

They read the project *before* they read the diff, then argue, then re-walk all
seven checks and confirm or withdraw every finding before anything is posted.
See [harness.md](ARCHITECTURE/harness.md) for the phases.

**Core languages: Python, C, C++ and Rust.** Each is first-class in the parts
of the tool that are language-aware — a measured indentation convention and a
repo baseline for check 1 (`repo_facts.INDENT_LANGS`), a symbol extractor
feeding check 3 (`repo_facts._symbols`), and a section in
`prompts/coding_styles.md`. A PR in any other language is still reviewed: the
panel derives the convention from the tree in `study_repo`, which is the same
thing it is told to do for these four when the file and the tree disagree. What
it loses is the measured leads — checks 1 and 3 start from nothing.

> **⚠ Needs kerness from `dev`, not the released wheel.** Getting all seven
> seats a turn took three fixes to the orchestrator loop itself; without them
> the chair stalls in the first phase and then writes a seven-check verdict
> covering seats that never spoke. `review.py` refuses to post such a run, so
> the failure is safe, but it is not a review. Cause and fixes are in
> [harness.md](ARCHITECTURE/harness.md#why-the-chair-drives-the-rotation-and-how-it-used-to-fail);
> the build is under [Target environment](#target-environment).

## Target environment

Linux/WSL with Python 3.10+, one dependency
([kerness](https://github.com/xwings/kerness), the multi-agent harness — see
`requirements.txt`), an authenticated `gh` CLI, and an OpenAI-compatible LLM
endpoint. Nothing about the machine is project-specific; see
[git-io.md](ARCHITECTURE/git-io.md) for how the branch a review is measured
against is resolved per repo.

kerness is not on PyPI, and the released wheel predates the orchestrator fixes
the panel depends on. Build it from its `dev` branch, into a working clone this
repo keeps beside it — `vendor/` is gitignored, and kerness stays its own
repository rather than becoming a gitlink in this one.

```sh
python3 -m venv .venv
git clone -b dev git@github.com:xwings/kerness.git vendor/kerness
.venv/bin/pip install maturin
cd vendor/kerness/bindings/python && ../../../../.venv/bin/maturin develop --release
cd ../../../.. && .venv/bin/python -m kerness.selfcheck   # expect "OK: all core checks passed"
```

## Invocation

```
./review.py <kind> <number> --repo REPO --api-key KEY --api-base URL --llm-model NAME

# examples
./review.py pr 7 --repo user/repo --llm-model gpt-5.6-luna --dry-run
./review.py issue 12 --repo https://github.com/user/repo --llm-model gpt-5.6-luna
./review.py pr 7 --repo git@github.com:user/repo.git --llm-model gpt-5.6-luna
```

- `<kind>`    — `pr` or `issue`
- `<number>`  — GitHub PR or issue number on the repo named by `--repo`

> **Breaking changes.** The old `<backend>` positional (`claude` / `codex`) is
> gone, along with the `reviewers/` package it selected: `./review.py claude pr
> 1233` is now `./review.py pr 1233 --repo <r> --llm-model <name>`. `--repo`
> itself used to carry a default repository and is now required — the tool
> reviews whatever it is pointed at and assumes no home project.

Required:

- `--repo REPO`        the repository to review. Accepts `OWNER/NAME` or any
                       github.com URL form — `github.com/o/n`,
                       `https://github.com/o/n[.git]`, `git@github.com:o/n.git`.
                       Other hosts are refused: every GitHub call goes through
                       `gh` (guardrail 1). No default, deliberately — a tool
                       that reviews one project by default is not a generic one.

Also required, each with an environment fallback so the key need not appear in
shell history:

- `--api-key KEY`      — or `$REVIEW_API_KEY`
- `--llm-model NAME`   — or `$REVIEW_MODEL`
- `--api-base URL`     — or `$REVIEW_API_BASE` (default: `https://api.openai.com/v1`)

**The API key is never persisted.** It is held in memory for the run: kerness is
constructed with `session_file=None`, the key is not logged, not written to
`--transcript`, and not stored anywhere on disk by this tool.

Optional flags:

- `--prompts PATH`      knowledge directory for this run, overriding the
                        `prompts/repos/` lookup ([Repo profiles](#repo-profiles))
- `--base-branch NAME`  branch to reset the checkout to, overriding the
                        PR's own base and the profile's pin
- `--dry-run`           run the review but print the result instead of posting
- `--allow-approve`     allow posting a real GitHub approval when the panel
                        proposes one; without it, approvals are posted as
                        comments with a note
- `--workdir PATH`      where to clone/checkout PRs (default: `./repo`)
- `--timeout SECONDS`   per-request HTTP timeout (default: 180)
- `--max-turns N`       override the gameplan's turn ceiling
- `--transcript PATH`   also write the panel transcript to a file

## Hard guardrails

These are constraints the script enforces in code, not just convention:

1. **All GitHub interaction goes through the `gh` CLI.** No direct REST/GraphQL
   calls, no `requests`/`httpx` to `api.github.com`, no PyGithub. Reasons:
   (a) reuses the maintainer's existing `gh auth login` so we never handle
   tokens, (b) one consistent audit surface for the deny-list. Enforced in
   [github-io.md](ARCHITECTURE/github-io.md).
2. **PR review always uses a fresh local branch.** The script refuses to run
   if the clone has uncommitted changes, and it always creates a new
   branch named `review/pr-<n>-<shortsha>` via `gh pr checkout`. Enforced in
   [git-io.md](ARCHITECTURE/git-io.md).
3. **No tests are executed.** The script never invokes `pytest`, `make`,
   build commands, or arbitrary scripts from the PR — and neither can the
   panel: kerness only exposes tools the gameplan declares, and
   `gameplans/pr_review.md` never declares `cmd`, so there is no path from PR
   content to a subprocess ([harness.md](ARCHITECTURE/harness.md)). File reads
   are confined to the checkout by a default-deny `AccessPolicy`. CI handles
   correctness.
4. **No merges, ever.** The only PR-write actions used are
   `gh pr review --approve` and `gh pr review --comment`. `gh pr merge` is
   never called and is explicitly blocked. Real approvals additionally
   require the `--allow-approve` flag.
5. **No issue closures.** The only issue-write action is `gh issue comment`.
   `gh issue close` is never called and is explicitly blocked.
6. **No pushes to the target remote.** The local branch stays local. `git
   push` (in any argv form, e.g. `git -C <dir> push`) is blocked, as are
   `gh api` and `gh repo sync`.

The deny-list wrapping every `gh`/`git` subprocess lives in
[github-io.md](ARCHITECTURE/github-io.md), so a future contributor who adds
a feature can't silently break rules 1, 4, 5, or 6.

## Repo profiles

What the panel *knows* about a project is per-repo; the seven checks and the
harness are not. That knowledge is a directory:

```
prompts/
├── coding_styles.md                 ← shared by every repo
├── default/                         ← the generic fallback profile
│   ├── ARCHITECTURE.md              ← "no curated map — build one from the tree"
│   ├── design.md                    ← project-agnostic rubric
│   └── profile.json                 ← {} — no base-branch pin
└── repos/                           ← empty: no profile ships
    ├── README.md                    ← the layout, and what belongs in each file
    └── <owner>/<name>/              ← yours, when you write one
        ├── ARCHITECTURE.md          ← the project's layering and API surface
        ├── design.md                ← the maintainer's rubric
        └── profile.json             ← {"base_branch": "..."}
```

Resolution (`review.py:142`, `resolve_profile`): `--prompts DIR` if given, else
`prompts/repos/<owner>/<name>/` if it exists, else `prompts/default/`. The
chosen profile is printed to stderr, so a run on the generic rubric never looks
curated.

Each file is looked up along **profile → `default/` → `prompts/`**
(`review.py:189`), so a profile carries only what it wants to say.
`coding_styles.md` stays shared unless a project overrides it — a project
outside the four core languages would.

To onboard a repo: create `prompts/repos/<owner>/<name>/`, write `design.md`
(and optionally `ARCHITECTURE.md`, `coding_styles.md`, `profile.json`). No
Python changes.

**`prompts/default/design.md` is not decorative — it is the common case.** The
tool ships no profile, so every review starts here until someone writes one.
That is also why no project's rubric may be the fallback: a panel handed one
project's layering rules and pointed at another would enforce them against code
that has none, and `require_completed_panel` would not catch it — a review that
reads authoritative and is wrong. The generic rubric defines the severity
vocabulary and approve threshold (the tool depends on both) and tells the panel
to derive conventions from the tree in `study_repo` rather than from the file.

## High-level flow

```
                ┌────────────────────────┐
   args ───────▶│  argparse + validation │
                │  normalize --repo URL  │
                │  resolve repo profile  │
                └──────────┬─────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       kind == "pr"               kind == "issue"
              │                         │
              ▼                         ▼
   ┌──────────────────┐       ┌──────────────────┐
   │ fetch PR via gh  │       │ fetch issue + cmts│
   │ checkout new br. │       │  via gh           │
   │ collect diff +   │       └────────┬──────────┘
   │ touched files    │                │
   └────────┬─────────┘                │
            ▼                          │
   ┌──────────────────┐                │
   │ repo_facts:      │                │
   │ measure indent,  │                │
   │ symbols, deps    │                │
   └────────┬─────────┘                │
            │                          │
            └────────────┬─────────────┘
                         ▼
            ┌────────────────────────┐
            │ build session topic    │
            │  (architecture+rubric+ │
            │   styles+facts+case)   │
            └────────────┬───────────┘
                         ▼
            ┌────────────────────────┐
            │ kerness panel          │
            │  study_repo            │
            │  → review_pr           │
            │  → cross_check         │
            │  → verify (rethink)    │
            └────────────┬───────────┘
                         ▼
            ┌────────────────────────┐
            │ typed result fields    │
            │  verdict, review_body, │
            │  findings, checklist   │
            │  (empty body → abort)  │
            └────────────┬───────────┘
                         ▼
            ┌────────────────────────┐
            │ post via gh            │
            │  pr  → review (appr/cm)│
            │  iss → comment         │
            └────────────────────────┘
```

## Workspace layout

```
codereview/
├── ARCHITECTURE.md             ← this file (AGENT.md, CLAUDE.md symlink to it)
├── ARCHITECTURE/               ← per-subsystem module docs (see Index)
├── .gitignore                  ← ignores .claude/, .codex/, repo/, vendor/, .venv/, __pycache__/
├── requirements.txt            ← kerness (the only dependency)
├── review.py                   ← CLI entry point (argparse, topic, verdict, posting)
├── session_builder.py          ← builds the kerness Session: provider, agents, policy, tools
├── repo_facts.py               ← deterministic pre-pass feeding checks 1, 3, 6
├── agent_tools.py              ← repo_grep, package_health, github_repo_health
├── github_io.py                ← all `gh` interactions (fetch, post, deny-list)
├── git_io.py                   ← clone, dirty-tree guard, fresh branch checkout
├── gameplans/
│   ├── pr_review.md            ← harness contract: 7 seats, 4 phases, result schema
│   └── issue_triage.md         ← harness contract: 2 seats, 2 phases
├── personas/                   ← one file per seat (7 PR + 2 issue + chair)
├── prompts/                    ← see [Repo profiles](#repo-profiles)
│   ├── coding_styles.md        ← check 1's ground truth, per language (shared)
│   ├── default/                ← generic fallback: ARCHITECTURE, design, profile
│   └── repos/<owner>/<name>/   ← per-repo knowledge; empty, none ships
├── repo/                       ← (gitignored) script-managed clone of the target
└── vendor/kerness/             ← (gitignored) kerness `dev` clone the wheel is built from
```

Rationale: the GitHub I/O and the panel are the two sides that change
independently. Who reviews and how is declared in `gameplans/` and `personas/`
and needs no Python change; what the panel knows about a specific project is
tuned in `prompts/repos/<owner>/<name>/`, also with no Python change.

## What's intentionally out of scope (v1)

- Running tests, builds, linters, type-checkers locally
- Inline review comments on specific lines (just a single review body for now)
- Multi-PR or batch mode
- Any kind of caching of past reviews
- Pushing branches anywhere
- Auto-merging, auto-closing, label management
- GitHub Enterprise or any host other than github.com
- Generating a repo's profile automatically from its tree
- First-class support for languages beyond Python, C, C++ and Rust — others are
  reviewed, but with no measured leads for checks 1 and 3

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

### Project-Specific Deviations

This repository has **no test runner and no `tests/` directory**. The suite is
the **How to Test** block of each module doc under `ARCHITECTURE/` — self-contained
`sh` and inline-`python` snippets whose passing evidence is a printed `ok …`
line and exit 0. Prove's survey rule applies to them unchanged: enumerate every
module doc's block and read the ones whose subject this change touches before
adding a case, and add the case to the block owned by the module under change
rather than opening a new one.

Two consequences strengthen the Definition of Done here:

- A change to a Python module is not proven until that module's owning doc's
  block runs green *as written in the doc*. A snippet that has drifted from the
  code is a failing test, not a stale comment.
- The end-to-end run is the only check that exercises the panel, needs `gh
  auth`, an LLM endpoint and network, and costs real tokens. It is listed in
  [review-cli.md](ARCHITECTURE/review-cli.md) as a manual step and is **not**
  part of the automated gate; a change to the topic builders, the gameplans or
  the personas is not done until it has been run once with `--dry-run`.

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

The seven checks above are the same seven the panel runs; this section is the
tool reviewing itself, and the two must not drift. Three additions:

- **[Hard guardrails](#hard-guardrails) are `blocker`s by construction.** A
  change that adds a GitHub call outside `github_io.gh`, exposes a `cmd`-like
  tool to the panel, reaches `gh pr merge` / `gh issue close` / `git push`, or
  persists the API key does not merge, whatever else it does. Check 7 owns
  guardrails 1, 4, 5 and 6; check 5 owns guardrails 2 and 3.
- **Check 6 has a standing answer here.** `requirements.txt` names exactly one
  dependency, kerness, built from source. A second top-level dependency is a
  `major` needing an explicit argument that the standard library will not do.
- **Check 1's own subject is versioned.** `prompts/coding_styles.md` is the
  rubric this project hands the panel; a change to the four core languages'
  conventions changes every future review, so it updates
  `repo_facts.INDENT_LANGS` and this file's core-languages note in the same
  change.

## Index

- [review-cli.md](ARCHITECTURE/review-cli.md) — CLI orchestrator: topic assembly, measured facts, result mapping, verdict policy (`--allow-approve`), posting.
- [harness.md](ARCHITECTURE/harness.md) — the panel: gameplans, phases, personas, tools, and the default-deny access policy that makes guardrail 3 structural.
- [github-io.md](ARCHITECTURE/github-io.md) — the `gh` chokepoint and the deny-list that enforces guardrails 1, 4, 5, 6.
- [git-io.md](ARCHITECTURE/git-io.md) — clone lifecycle, fresh review branches, and base-branch resolution (why a profile may pin a branch).
- [prompts.md](ARCHITECTURE/prompts.md) — the knowledge layers and the repo-profile lookup: architecture, review rubric, per-language style.
