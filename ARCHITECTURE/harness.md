---
eatmycode_version: "1.2.0"
---
# Review panels and runtime

## Goal

Provide M1's architecture preparation, PR review and issue investigation panels.
Gameplans define tool and result contracts; personas supply review expertise.
The runtime selects bounded PR/issue turns and authenticates their results before
the CLI may publish. Documentation preparation keeps its automatic phased panel.

## Status

`done` — all three panel contracts and strict completion/assessment gates pass the
offline workflow suite. `patches/README.md:25` records the dependency patch's
historical upstream verification; current changes require the checks below. Live model reasoning is unverified offline.

## Code Structure

| File | Role |
| ---- | ---- |
| `session_builder.py` | Provider, workspace, registered agents and tools for each panel |
| `panel_runtime.py` | Host routing, display progress, strict run outcomes and authenticated results |
| `gameplans/pr_review.md` | Lead, optional consultants, Verifier, seven checks and result protocol |
| `gameplans/issue_triage.md` | Investigation, conditional verification and issue result protocol |
| `gameplans/architecture_docs.md` | Planner, writer and verifier producing proposed architecture documents |
| `personas/*.md` | Specific expertise and boundaries for reviewers, investigators, documentation agents and chair |
| `agent_tools.py` | Tracked-file search, PyPI advisory/metadata lookup and GitHub upstream metadata |
| `patches/kerness-pyo3.patch` | Reproducible PyO3 security update against the pinned public kerness source |

## Language and Conventions

Python binds a declarative Markdown/YAML harness to kerness; personas are
Markdown instructions. Follow [root Python conventions](../ARCHITECTURE.md#coding-style-and-code-design).
`session_builder.py:36` is the canonical session/access-policy constructor;
`panel_runtime.py:151` owns completion validation. Roster identifiers are
protocol values shared with gameplans, not display names. The only extension
dependency is the pinned patched kerness build described in `patches/README.md`.
No local formatter/type-checker configuration exists.

## Design and Invariants

Session construction owns provider/agent/tool binding; runtime validation owns
observed participation and stage results; reporting owns nested validation and
assembly. Gameplans own protocol instructions, explicitly delivered to agents. Model
and repository text cannot grant tools or forge attributed history. Host code
uses the strict owned run API and never treats coerced defaults as evidence.
Session persistence is disabled; transcripts are opt-in and failures propagate.
The access policy grants named guide files outside the reviewed source, not the
whole guide worktree. No gameplan declares command or write tools. All source
searches go through Git and metadata tools use the audited GitHub boundary or
explicit PyPI/OSV endpoints (`agent_tools.py:60`, `agent_tools.py:180`).

## Key Types and Entry Points

- `session_builder.py:27` — `build_provider` constructs an OpenAI-compatible
  endpoint without persisting its key.
- `session_builder.py:36` — `_build` confines source reads to the selected or
  locally merged working tree, grants individual prepared documentation files,
  binds a panel and disables persistent session state and inter-turn delays.
- `session_builder.py:106` — `build_pr_session`; issue and documentation
  builders select their corresponding gameplans and rosters below it.
- `panel_runtime.py:15` — `PANELS` holds stable routing IDs/personas;
  `PHASES` is documentation-only and `TITLES` owns human display names.
- `panel_runtime.py:47` — `PanelChannel` prints completed PR/issue
  steps and documentation phase/turn counts on stderr.
- `panel_runtime.py:93` — `PanelResult` carries strict fields,
  authenticated history, engine counters, usage and independent assessments.
- `panel_runtime.py:151` — `validate_panel` replays the required
  sequence and proves final fields/assessments match attributed stage records.
- `panel_runtime.py:256` — `run_session` requires a source checkout
  for PR/issues, drives host-selected turns, and rejects incomplete outcomes.
- `agent_tools.py:60` — `make_repo_grep` searches tracked files through the
  audited Git wrapper; package and upstream metadata tools complement it.

All reviews read architecture, related documents and full relevant source before
concluding. PR and issue sessions have no orchestrator or phase rotation. The
host delivers trusted gameplan instructions to the participants; their Markdown
body alone is not automatically included by kerness. Persona instructions use
sections that kerness actually loads. Repository/profile prose cannot grant tools
or replace the protocol.

| Review | Required sequence | Agent turns |
| ---- | ---- | ---- |
| PR | Lead → requested Security → requested Dependencies → Verifier | 2–4 |
| Issue | Investigator → Verifier when required | 1–2 |
| Documentation | Chair routes DocsPlanner, DocsWriter, DocsVerifier in `plan`, `draft`, `verify` | 9 specialist turns plus chair calls |

Each PR/issue turn ends with one `RESULT {JSON}` line. The host validates the
stage before proceeding and captures engine `turn_committed` events, then checks
those events against final history. Agent names in prose cannot impersonate a
reviewer. `select_agent` controls order; `finish` validates final fields without
another model call. The host derives results from authenticated records, since
engine finalization alone can succeed without required participation. Exhausted
turn limits, invalid stage records and unexpected waits stop publication.

Lead covers all seven separate checks, optionally requests each consultant once
with a focused question, and supplies a recommendation. Consultants return
findings, questions and an evidence summary. Verifier independently checks even
a clean review, accounts for every indexed candidate with a cited confirmation,
withdrawal or unresolved disposition, and supplies the final assessment and new
findings. [Reporting](reporting.md) assembles the result and preserves differing
recommendations and unresolved questions. No new review loop starts afterward.
Fit retains `Need: justified`, `Need: unclear` or `Need: unnecessary`; missing
context is a concern, not a fabricated code defect.

An issue uses Investigator's `verify` flag and classification to select its route.
Only `support` and `needs_information` with `verify=false` finish in one turn.
All other classifications and requested verification run Verifier once. Prompts
require verification for uncertainty, substantial reasoning, suggested repairs
and consequential advice. The host cannot infer semantic complexity independently
of those fields. Earlier unanswered questions remain visible conservatively.

When a documentation panel runs, it requires the actual final DocsVerifier turn to
end with `DOCS_AUDIT {"accepted":true,"reason":"Source evidence checked."}`.
The runtime rejects a missing, malformed or negative record, and requires the
chair's `audited` field to be true as well. The chair cannot overrule an
independent documentation rejection. [Preflight](architecture-preflight.md) may
skip preparation when root, module and supporting-page versions all match and
every architecture file fits the size limit. Reuse does not audit document
content or structure. PR/issue topics disclose the skipped checks and still
require full relevant source reads. Reused guides live in the source snapshot
and need no additional file grants; generated guides live in separate worktrees.

Default progress uses engine events to identify each model wait and evidence
inspection before it starts; only known display identities and host-authored
operation descriptions are printed. Event payloads, tool arguments, source and
model text are excluded. The [workflow](review-cli.md) owner's `progress.activity`
adds a flushed heartbeat every 15 seconds, including during blocked provider
calls, and stops its thread on every panel exit. Completion is printed only after
strict outcome and participation validation. PR/issue completion shows the step
and reviewer; documentation shows phase and specialist-turn counts. Counts are
observations and never substitute for validation.

Output does not repeat chair chatter and raw JSON by default. The optional raw
transcript is delivered directly so a write failure stops the run; kerness's
fan-out channel intentionally suppresses member failures and therefore is not
suitable for this required audit artifact. Transcript destinations are declared
to the same access policy as the checkout.

When prepared documents live in a separate worktree, only its root
`ARCHITECTURE.md` and Markdown files recursively under `ARCHITECTURE/` receive
individual additional read grants, including nested supporting pages. Other
files in that worktree remain inaccessible. Source reads and searches continue against the selected-branch or locally merged source
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

The workflow suite must exit zero and exercise real scripted host-driven
reviews, consultant selection, conditional issue verification, actual prompt
delivery, per-agent attribution, finding accounting and dissent. It also covers
strict errors, turn limits, unchanged documentation audits, progress, blocked-model
heartbeats, tool confinement and transcript success/failure. Kerness selfcheck must print
`OK: all core checks passed`. For dependency patch changes, the binding suite
must pass and Rust test/clippy commands must exit zero; recorded historical
counts in `patches/README.md:25` are not a substitute for a new run. The vendor
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

Routing changes must update `PANELS`, host selection/replay, gameplans and
completion checks together, then pass real scripted-session integration tests.
Documentation phase changes also update `PHASES`. Preserve engine-attributed
records and independent documentation vetoes. Check the actual provider messages
when changing personas or gameplans; supported Markdown parsing is selective. Tool additions require reviewing both
registry and gameplan exposure, file confinement and bounded output. Provider
or kerness API changes must run selfcheck and the workflow suite from a public
reproducible build. Dependency patch changes also require the optional upstream
checks in How to Test and renewed advisory/license evidence.

## Open Gaps / Roadmap

- Participation and assessment identity are enforced; semantic understanding
  and source interpretation remain model-dependent. Independent verification
  and maintainer review remain necessary.
- PR review is bounded to 2–4 turns, issues to 1–2; tool followups and context
  compaction can add provider requests within a turn. Documentation preparation
  still has chair routing and closing calls when the architecture gate requires it.
- Package advisory coverage is PyPI-specific; other ecosystems need additional
  evidence and must not be reported as verified when evidence is absent.
- Model calls are synchronous. Heartbeats show elapsed waiting time, not token
  streaming or provider health; cancellation cannot forcibly interrupt a blocked
  provider call.
