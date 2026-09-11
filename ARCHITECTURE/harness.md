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
| `provider_io.py` | Observe assembled HTTP payload sizes, attempts and usage while preserving native retry policy |
| `gameplans/pr_review.md` | Lead, optional consultants, Verifier, seven checks and result protocol |
| `gameplans/issue_triage.md` | Investigation, conditional verification and issue result protocol |
| `gameplans/architecture_docs.md` | Planner, writer and verifier producing proposed architecture documents |
| `personas/*.md` | Specific expertise and boundaries for reviewers, investigators, documentation agents and chair |
| `agent_tools.py` | Tracked-file search, PyPI advisory/metadata lookup and GitHub upstream metadata |
| `patches/kerness-pyo3.patch` | Reproducible PyO3 security update against the pinned public kerness source |

## Language and Conventions

Python binds a declarative Markdown/YAML harness to kerness; personas are
Markdown instructions. Follow [root Python conventions](../ARCHITECTURE.md#coding-style-and-code-design).
`session_builder.py:39` is the canonical session/access-policy constructor;
`panel_runtime.py:169` owns completion validation. Roster identifiers are
protocol values shared with gameplans, not display names. The only extension
dependency is the pinned patched kerness build described in `patches/README.md`.
No local formatter/type-checker configuration exists.

## Design and Invariants

Session construction owns provider/agent/tool binding; runtime validation owns
observed participation and stage results; reporting owns nested validation and
assembly. Gameplans own protocol instructions, explicitly delivered to agents. Model
and repository text cannot grant tools or forge attributed history. Host code
uses the strict owned run API and never treats coerced defaults as evidence.
Routing and replay own bounded format correction (`panel_runtime.py:239`,
`panel_runtime.py:135`). Live steps validate before routing; replay validates
the initial route and delegates remaining stage validation to report assembly.
Session persistence is disabled; transcripts are opt-in and failures propagate.
The access policy grants named guide files outside the reviewed source, not the
whole guide worktree. No gameplan declares command or write tools. All source
searches go through Git and metadata tools use the audited GitHub boundary or
explicit PyPI/OSV endpoints (`agent_tools.py:60`, `agent_tools.py:180`).

`build_provider` (`session_builder.py:28`) gives each model request two retries
after the initial attempt, including network timeouts and HTTP errors. It sets
`interval_sec=30` in kerness, overriding the default linear backoff with a fixed
30-second pause after each failure before retrying. A retry sequence permits
three attempts and one minute of waits, plus request time. All three panels share this provider policy;
retries resend the pending request without restarting completed turns. `--timeout`
applies separately to each attempt. Existing
provider fallback behavior and sanitized terminal diagnostics remain in place;
a fallback can start another retry sequence. Waiting does not resolve a
persistent HTTP 400 caused by an incompatible request.

`provider_io.ObservedProvider` retains native `chat_with_retries` and observes the
public `kerness.provider.http_post_json` seam after payload assembly. Every POST
reports its logical request, attempt, retry and fallback sequence, serialized
JSON sizes and HTTP duration. Transport failures announce the configured next
retry pause using shared policy constants. Native empty-response or decoding
failures are outside this transport seam; their retries are visible on the next
attempt but have no immediate transport-error pause notice. Recursive native
compatibility fallbacks reset the attempt counter without allocating a new
logical request. Native compaction lacks a `provider_started` event, so the
observer assigns it a request and `compact` phase, attributed to Chair for docs
or the first registered reviewer otherwise.

Measurements include message count and JSON bytes, fixed role-byte buckets,
tool-schema count/JSON bytes and total payload JSON bytes, using compact UTF-8
serialization. Role sizes sum serialized message objects without array
delimiters. Estimated tokens are message/schema JSON characters divided by four;
this is a heuristic, not a model tokenizer, context limit or proof of timeout
cause. Payload serialization can differ from native wire formatting for numbers;
headers are excluded. Only nonnegative integer provider `prompt_tokens` or
`input_tokens` usage is emitted separately. No payload content, schema names,
raw errors, endpoint URLs, headers or credentials enter these measurements.

The observer uses panel/request ContextVars and an RLock around scoped global
transport replacement. Observed calls serialize; unrelated threads delegate
through without logging. `finally` restores the transport and request context
on success or failure. A stderr write error is deferred until the outer native
retry operation returns, so broken telemetry cannot replay a successful POST.
The hook is active only inside observed calls in a panel; direct provider calls
outside a panel retain native behavior. This module imports no CLI or runtime
owner; both runtime and session construction depend on it.

`run_session` supplies kerness's `max_elapsed_ms` budget, defaulting to 900 seconds
per panel via `--panel-timeout`. It includes every reviewer, tool followup,
compaction, retry and fallback; a tool response cannot restart the clock.
The budget is cooperative at engine action boundaries: an active HTTP attempt
and remaining native retry pauses can overrun it. A host monotonic check before
accepting the outcome also covers native closing paths that fail to recheck the
budget after their final response. Expiry stops publication even if that
response contains a valid result. A specific elapsed-budget
diagnostic replaces the generic engine error. There is no separate tool-iteration
cap that might accept text while tool calls remain pending. The PR gameplan asks
reviewers to batch independent evidence reads, reuse inspected source and finish
once all seven checks have evidence, recording unresolved gaps without speculation.

## Key Types and Entry Points

- `session_builder.py:28` — `build_provider` constructs an OpenAI-compatible
  endpoint without persisting its key.
- `session_builder.py:39` — `_build` confines source reads to the selected or
  locally merged working tree, grants individual prepared documentation files,
  binds a panel and disables persistent session state and inter-turn delays.
- `panel_runtime.py:17` — `PANELS` holds stable routing IDs/personas;
  `PHASES` is documentation-only; progress uses the registered agent names.
- `panel_runtime.py:47` — `PanelChannel` delivers optional verbose agent/system
  exchanges and transcripts; compact status comes from runtime events.
- `panel_runtime.py:84` — `PanelResult` carries strict fields,
  authenticated history, engine counters, usage and independent assessments.
- `panel_runtime.py:169` — `validate_panel` replays the required
  sequence and proves final fields/assessments match attributed stage records.
- `panel_runtime.py:309` — `run_session` requires a source checkout
  for PR/issues, drives host-selected turns with an elapsed budget, and rejects incomplete outcomes.
- `agent_tools.py:60` — `make_repo_grep` searches tracked files through the
  audited Git wrapper; package and upstream metadata tools complement it.
- `provider_io.py:67` — `observe_requests` scopes panel attribution and request
  IDs; `ObservedProvider` below observes actual POST attempts and restores transport.

All reviews read architecture, related documents and full relevant source before
concluding. PR and issue sessions have no orchestrator or phase rotation. The
host delivers trusted gameplan instructions to the participants; their Markdown
body alone is not automatically included by kerness. Persona instructions use
sections that kerness actually loads. Repository/profile prose cannot grant tools
or replace the protocol.

| Review | Required sequence | Agent turns including format corrections |
| ---- | ---- | ---- |
| PR | Lead → requested Security → requested Dependencies → Verifier | 2–4 stages, at most 8 turns |
| Issue | Investigator → Verifier when required | 1–2 stages, at most 4 turns |
| Documentation | Chair routes DocsPlanner, DocsWriter, DocsVerifier in `plan`, `draft`, `verify` | 9 specialist turns plus chair calls |

Gameplans request one terminal `RESULT {JSON}` line. The shared parser
(`panel_runtime.py:96`) also accepts indented or multiline JSON, a complete
terminal triple-backtick JSON fence around the record or its payload, and a
response consisting solely of a JSON object with an optional fence. It parses
the entire payload, rejecting duplicate records, incomplete JSON and trailing
prose; it never extracts bare objects from arbitrary prose. These formats use
the same validation in both verbosity modes and require no correction.
A missing record or malformed JSON permits exactly one additional turn by the same actor to
correct the format, preserving the findings, evidence, questions and conclusion.
Schema and citation errors remain terminal. Both attempts stay in the engine
history and transcript; replay accepts a correction only immediately after that
actor's invalid attempt and rejects duplicate valid results or a second invalid
attempt. Default gameplan ceilings
are 8 PR turns or 4 issue turns and two engine rounds, allowing a correction for
each required stage without reopening the review. Explicit `--max-turns` still
limits the whole panel. Correction prompts include the parser's failure reason.
Exhausted corrections explain that no complete model result was supplied;
verbosity only controls logging. The response is not printed by default.
The host validates the stage before proceeding and captures engine
`turn_committed` events, then checks those events against final history.
Agent names in prose cannot impersonate a
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

Default progress combines engine events and the provider observer to count logical model requests and identify each model wait, evidence
inspection and committed specialist turn. The common format is
`[YYYY-MM-DD HH:MM:SS] [model] [agent] [phase]`; model names come from the
registered agents and operation descriptions are host-authored. Raw event
payloads, tool arguments, source and model text are excluded. PR/issue stages
use `review` or `verify`. Kerness events do not expose phase names, so docs
`plan`, `draft` and `verify` follow the required specialist rotation, excluding
Chair turns; final-summary provider purpose selects `summary`. These observations
never substitute for participation validation. The [workflow](review-cli.md)
owner's `progress.activity` retains model/agent/phase in its flushed heartbeat,
scheduled every 15 seconds, and stops its thread on normal or exceptional panel exit. A committed turn
is distinct from successful panel completion, which follows strict validation.
Heartbeat totals measure the full panel duration across activity changes;
request counts exclude the separately labeled native attempts inside each logical request.
Prompt metrics and safe HTTP outcomes are separate status lines; they never enter
agent messages, reports or transcripts. Review topics identify the inlined root
guide for reuse, avoiding a duplicate tool read while requiring relevant modules
and complete source. Original architecture is still read when the guide is separate.

Output does not repeat chair chatter, system messages or raw JSON by default.
`--verbose` emits full agent/system exchanges with the same prefix. All panels report engine failures through one formatter: failure reason and
actual error category, with HTTP status or a request-timeout indication when
available. The engine end state is used only when no error exists; a network
failure must not be mislabeled by the engine's fallback `max_turns` state.
Provider URLs, raw causes and response bodies stay out of the diagnostic.
A review that finishes before a required agent uses the same formatter.
The optional raw
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
strict errors, formatted JSON in both verbosity modes without a transcript,
corrected results with retained history, rejected correction/actor
tampering, correction exhaustion, turn limits, unchanged documentation audits,
progress, blocked-model heartbeats, tool confinement and transcript success/failure.
The provider retry regression uses the real provider and engine with a mocked
HTTP transport. It asserts the configured 30-second interval, then disables
both interval and backoff waits in the fixture: PR, issue and documentation
panels recover from timeouts and HTTP 400 on retry two, retain completed turns,
and stop with sanitized errors after three failed attempts. Successful requests do
not retry, and each attempt keeps its timeout. Empty replies retry too; tool and
reasoning compatibility fallbacks keep logical IDs and reset attempt counters.
Measurement checks inspect actual native POST payloads, including Unicode,
native schemas and successful file-read results, assert role/byte/estimate counts
and provider-usage handling, and keep contents out of progress. Observation checks
cover compaction attribution, unrelated threads, transport restoration and output
failures without replaying successful calls.
Native elapsed-budget cases reject both late valid responses and pending tool
calls across all three panels. A subprocess regression sends SIGINT during real
native HTTP against a local fixture server and during native retry sleep; the
CLI must terminate promptly with SIGINT and no report. These tests make no
external provider calls or GitHub writes.
Kerness selfcheck must print
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
- PR review is bounded to 2–4 stages, issues to 1–2, with at most one additional
  format-correction turn per stage. Tool followups and context compaction can add
  provider requests within the shared elapsed budget. Documentation preparation
  still has chair routing and closing calls when the architecture gate requires it.
- Package advisory coverage is PyPI-specific; other ecosystems need additional
  evidence and must not be reported as verified when evidence is absent.
- Model calls are synchronous. Heartbeats show elapsed waiting time, not token
  streaming or provider health. The elapsed budget is cooperative, and imported
  library calls retain the caller's signal handling; the CLI's OS SIGINT action
  terminates blocked native calls immediately. Native retry sleeps can delay Python heartbeats: a simulated
  HTTP 400 with the 30-second retry interval emitted its first heartbeat after
  30 seconds despite the 15-second schedule.
