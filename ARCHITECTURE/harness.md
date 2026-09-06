---
eatmycode_version: "1.1.0"
---
# Review panels and runtime

## Goal

Provide M1's architecture preparation, PR review and issue investigation panels.
Gameplans define the phases and result contracts; personas supply distinct
professional responsibilities; the runtime verifies completion and attributes
merge ballots before the CLI may publish a result.

## Status

`done` — all three panel contracts and strict completion/vote gates pass the
offline workflow suite. Recorded dependency-patch verification covers the
upstream Python binding/Rust suites, clippy and kerness selfcheck; current
changes require the checks below. Live model reasoning is unverified offline.

## Code Structure

| File | Role |
| ---- | ---- |
| `session_builder.py` | Provider, workspace, registered agents and tools for each panel |
| `panel_runtime.py` | Rosters, display names, phase/turn progress, strict run outcomes and ballot attribution |
| `gameplans/pr_review.md` | Seven reviewers, five phases and PR result contract |
| `gameplans/issue_triage.md` | Two investigators, three phases and issue result contract |
| `gameplans/architecture_docs.md` | Planner, writer and verifier producing proposed architecture documents |
| `personas/*.md` | Specific expertise and boundaries for reviewers, investigators, documentation agents and chair |
| `agent_tools.py` | Tracked-file search, PyPI advisory/metadata lookup and GitHub upstream metadata |
| `patches/kerness-pyo3.patch` | Reproducible PyO3 security update against the pinned public kerness source |

## Language and Conventions

Python binds a declarative Markdown/YAML harness to kerness; personas are
Markdown instructions. Follow [root Python conventions](../ARCHITECTURE.md#coding-style-and-code-design).
`session_builder.py:38` is the canonical session/access-policy constructor;
`panel_runtime.py:141` owns completion validation. Roster identifiers are
protocol values shared with gameplans, not display names. The only extension
dependency is the pinned patched kerness build described in `patches/README.md`.
No local formatter/type-checker configuration exists.

## Design and Invariants

Session construction owns provider/agent/tool binding; runtime validation owns
observed participation and ballots; gameplans own phase instructions. Model
and repository text cannot grant tools or forge attributed history. Host code
uses the strict owned run API and never treats coerced defaults as evidence.
Session persistence is disabled; transcripts are opt-in and failures propagate.
The access policy grants named guide files outside the reviewed source, not the
whole guide worktree. No gameplan declares command or write tools. All source
searches go through Git and metadata tools use the audited GitHub boundary or
explicit PyPI/OSV endpoints (`agent_tools.py:60`, `agent_tools.py:180`).

## Key Types and Entry Points

- `session_builder.py:29` — `build_provider` constructs an OpenAI-compatible
  endpoint without persisting its key.
- `session_builder.py:38` — `_build` confines source reads to the selected or
  locally merged working tree, grants individual prepared documentation files,
  binds a panel and disables persistent session state and inter-turn delays.
- `session_builder.py:101` — `build_pr_session`; issue and documentation
  builders select their corresponding gameplans and rosters below it.
- `panel_runtime.py:14` — `PANELS` holds stable routing IDs and persona files;
  `PHASES` and `TITLES` define the runtime contract and human display names.
- `panel_runtime.py:57` — `PanelChannel` prints phase and specialist-turn counts on stderr;
  verbose output and an optional complete transcript preserve detailed turns.
- `panel_runtime.py:102` — `PanelResult` carries strict fields, authenticated
  history, phase counters, usage and separately attributed votes.
- `panel_runtime.py:141` — `validate_panel` requires every phase and every
  participant turn, then parses each specialist's own final ballot.
- `panel_runtime.py:191` — `run_session` drives the owned kerness run with
  strict result validation and rejects unsuccessful or incomplete outcomes.
- `agent_tools.py:60` — `make_repo_grep` searches tracked files through the
  audited Git wrapper; package and upstream metadata tools complement it.

All panels read `ARCHITECTURE.md`, related `ARCHITECTURE/` documents and full
source before drawing conclusions. Repository/profile prose is evidence, not
permission to replace the workflow or expose additional tools.

| Panel | Specialists | Phases |
| ---- | ---- | ---- |
| PR | Language/tooling, API design, refactoring, senior engineering, architecture, supply chain and security | `study_repo`, `review_pr`, `cross_check`, `verify`, `vote` |
| Issue | Failure analysis and product/architecture triage | `study_repo`, `investigate`, `verify` |
| Documentation | Architecture planner, writer and verifier | `plan`, `draft`, `verify` |

A chair routes the fixed roster through every phase. In PR cross-checking every
specialist argues a position and answers the strongest opposing evidence; in
verification the panel confirms or withdraws findings. Fit preserves its
`Need: justified`, `Need: unclear` or `Need: unnecessary` conclusion in
`checklist.fit.note`. Missing context stays a concern without a fabricated
finding; justified need does not erase architectural problems.

The last specialist turn ends with one line:

```text
BALLOT {"vote":"merge","reason":"Evidence and response to the strongest objection."}
```

Votes may be `merge`, `hold` or `reject`. The runtime reads the seven ballots
from engine-attributed participant history, never from the chair's description
of what others voted. The chair contributes its own `chair_vote` result field.
Approval requires eight merge votes, completed checks, no major/blocker findings
and the applicable rubric's threshold. The CLI implements this final decision
and posting policy. An incomplete run cannot become a comment masquerading as a
completed review.

Kerness's exact completed-round count and forward-only phases, combined with
an exact recorded rotation, establish that all required seats spoke in every
phase. Merely reaching the last phase does not pass. Strict result validation
also rejects missing or incorrectly typed fields; the older `Session.run()`
coercion path is not used.

When a documentation panel runs, it requires the actual final DocsVerifier turn to
end with `DOCS_AUDIT {"accepted":true,"reason":"Source evidence checked."}`.
The runtime rejects a missing, malformed or negative record, and requires the
chair's `audited` field to be true as well. The chair cannot overrule an
independent documentation rejection. [Preflight](architecture-preflight.md) may
skip preparation when the root document version matches, without inspecting
modules or content. PR/issue topics disclose the skipped checks and still
require full relevant source reads. Reused guides live in the source snapshot
and need no additional file grants; generated guides live in separate worktrees.

Default progress uses engine events to identify each model wait and evidence
inspection before it starts; only known display identities and host-authored
operation descriptions are printed. Event payloads, tool arguments, source and
model text are excluded. The [workflow](review-cli.md) owner's `progress.activity`
adds a flushed heartbeat every 15 seconds, including during blocked provider
calls, and stops its thread on every panel exit. Completion is printed only after
strict outcome and participation validation. Specialist completion shows the
phase number/name and completed turns out of the required total; counts are
observations and never substitute for validation.

Output does not repeat chair chatter and raw JSON by default. The optional raw
transcript is delivered directly so a write failure stops the run; kerness's
fan-out channel intentionally suppresses member failures and therefore is not
suitable for this required audit artifact. Transcript destinations are declared
to the same access policy as the checkout.

When prepared documents live in a separate worktree, only its root
`ARCHITECTURE.md` and direct `ARCHITECTURE/*.md` files receive additional read
grants. Other files in that worktree remain inaccessible. Source reads and
searches continue against the selected-branch or locally merged source
repository. PR locations refer to the merge result and may differ from the
GitHub PR head; generated guides never supply finding citations.

No gameplan declares commands, writes, or executable skills. Kerness narrows
registered tools to each gameplan's list. Built-in file/directory reads enforce
the workspace; `repo_grep` is a fixed Git search with an option-separated pattern
and optional pathspec. The package tool supplies PyPI/OSV evidence; GitHub
metadata does not establish advisories for arbitrary package ecosystems.

## Interactions

- [review-cli.md](review-cli.md) builds topics, runs panels, validates source
  citations and renders/publishes the final result.
- [prompts.md](prompts.md) supplies supplementary repository profiles and rubrics.
- [git-io.md](git-io.md) prepares isolated branch/local-merge sources and
  separate documentation worktrees.
- [github-io.md](github-io.md) confines GitHub interactions to audited commands.
- Architecture preparation calls the documentation panel for proposed markdown;
  the host validates and materializes it, while model tools remain read-only.

## How to Test

From the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m kerness.selfcheck
```

For dependency patch development only, after building the public pinned
checkout under `vendor/kerness/` and installing its test prerequisites:

```sh
.venv/bin/python -m pytest vendor/kerness/bindings/python/tests -q
cargo test --manifest-path vendor/kerness/Cargo.toml -p kerness --locked
cargo clippy --manifest-path vendor/kerness/Cargo.toml --workspace --all-targets --locked -- -D warnings
```

The workflow suite must exit zero and exercise actual scripted panel rounds,
strict result errors, per-agent ballot attribution, dissent, early termination,
phase/turn output, blocked-model heartbeats, evidence-inspection events and
transcript delivery. Kerness selfcheck must print
`OK: all core checks passed`; the binding suite passes 502 tests and the Rust
test/clippy commands exit zero. The vendor
suite is optional for installations without a local source checkout, while the
workflow suite and selfcheck remain required.

The dependency starts from public upstream commit
`7c97dcb4e50a8fd05d05185b0052ba1356be016a`, then applies the tracked
`patches/kerness-pyo3.patch`. Upstream PyO3 0.23.5 has RUSTSEC-2025-0020 and
RUSTSEC-2026-0177 advisories; the patch updates it to 0.29.2 and adapts binding
API names, conversion bounds and explicit clone extraction. The lockfile pins
the new versions. Applying the patch to a pristine archive of the public commit
reproduces the tested source byte-for-byte. Kerness's owned run API and custom
channel seam already support the workflow; no core runtime patch was needed.
After updating Python source, rebuild the Rust binding too; a stale extension
previously caused `ImportError: cannot import name 'RunControl'` before
selfcheck could start.

## Review and Refactor Guide

Roster/phase changes must update `PANELS`, `PHASES`, gameplans and completion
checks together, then pass real scripted-session integration tests. Preserve
engine-attributed final records and independent documentation vetoes; prose
from the chair cannot replace them. Tool additions require reviewing both
registry and gameplan exposure, file confinement and bounded output. Provider
or kerness API changes must run selfcheck and the workflow suite from a public
reproducible build. Dependency patch changes also require the optional upstream
checks in How to Test and renewed advisory/license evidence.

## Open Gaps / Roadmap

- Participation and ballot identity are enforced; semantic understanding of
  every source read and the quality of debate cannot be proved from prose.
  Source citations, cross-examination and maintainer review remain necessary.
- Every PR requires 35 specialist turns plus chair routing and two closing
  passes. `--max-turns` can limit cost, but an exhausted run cannot publish.
- Package advisory coverage is PyPI-specific; other ecosystems need additional
  evidence and must not be reported as verified when evidence is absent.
- Model calls are synchronous. Heartbeats show elapsed waiting time, not token
  streaming or provider health; cancellation cannot forcibly interrupt a blocked
  provider call.
