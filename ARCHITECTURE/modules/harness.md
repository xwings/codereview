---
eatmycode_version: "2.0.0"
---
# Review panels and runtime

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `panel_runtime.py`, `session_builder.py`, `provider_io.py`,
`agent_tools.py`, PR/issue gameplans, non-doc personas, binding integration or
panel execution, evidence access and authenticated completion.

## Responsibility and Status

Construct read-only review sessions, route bounded PR/issue turns, run phased
documentation panels and authenticate results before publication. `done` — implemented;
offline scripted kerness sessions cover protocol, access and failure behavior.
Live model reasoning remains unverified. Documentation content contracts belong
to the preflight owner.

## Code Map

| Path / symbol | Role |
| ------------- | ---- |
| `session_builder.py:_build` | Provider, roster, tool and access-policy binding |
| `panel_runtime.py:run_session`, `validate_panel` | Host selection, budgets and authenticated result replay |
| `provider_io.py:ObservedProvider` | Actual HTTP attempt/size/usage observation |
| `agent_tools.py:make_repo_grep` | Bounded tracked-file search; adjacent metadata tools |
| `gameplans/`, `personas/`, `tests/test_workflow.py`, `patches/`, `requirements.txt` | Protocol/expertise, integration tests and pinned dependency |

## Local Conventions

Use [root conventions](../../ARCHITECTURE.md#code-conventions). Roster names are
protocol values shared with gameplans. Gameplans use YAML frontmatter/Markdown;
persona sections must be ones kerness actually loads. Read [kerness integration](../topics/kerness-integration.md) when changing
binding APIs, dependency pins/patches or build assumptions.

## Contracts and Invariants

Construction owns binding; runtime owns observed participation and stage
records; reporting owns nested validation/assembly. Trusted gameplan bodies are
explicitly delivered to PR/issue participants. Repository/profile/model prose
cannot expand tools, change roles or forge sender identity. Session persistence
is disabled; optional transcript failures propagate. No gameplan declares a
command, write, memory-write or executable-skill tool.

Source reads stay in the selected/merged checkout. Separate guides receive
individual grants for root and architecture Markdown, never a blanket worktree
grant; unrelated files/archives remain inaccessible. Source finding citations
cannot use generated guide lines. Built-in reads reject escapes; `repo_grep`
uses fixed `git grep` argv with option-separated pattern/pathspec and caps output
at 80 lines of 300 characters. Metadata failures return explicit unavailable
evidence; package health is PyPI/OSV-specific and GitHub metadata goes through
`github_io.gh`. Missing ecosystem evidence never means a passed dependency check.

Reviewers use the compact root and mandatory AGENT_RULES, follow Task Index to
the relevant owner and matching topics, and inspect complete relevant source.
Reuse pages already available in context. Read partner modules only for affected
contracts/data flow and handle broad changes in bounded owner batches. Discovery
starts from changed paths or issue symbols; it does not expand all doc links.

| Panel | Required route | Stage/turn bounds |
| ----- | -------------- | ----------------- |
| PR | Lead → requested Security → requested Dependencies → Verifier | 2–4 stages; at most 8 turns including corrections |
| Issue | Investigator → Verifier when required | 1–2 stages; at most 4 turns including corrections |
| Docs | Chair rotates DocsPlanner, DocsWriter, DocsVerifier in plan/draft/verify | 9 specialist turns plus chair calls |

Lead covers seven checks and requests each consultant at most once. Verifier
checks even clean reviews and every candidate; no later review loop starts.
Issue routing uses classification/verify fields, not inferred semantic complexity.
[Reports](reporting.md) owns exact assessment/finding and issue-routing rules.

`_final_record` accepts terminal `RESULT` JSON, ordinary indentation/line breaks,
complete terminal triple-backtick JSON fences, or a response solely containing a
JSON object (optionally fenced). It parses the entire payload, rejects duplicate
records/trailing prose/incomplete JSON and never mines objects out of prose.
Missing/malformed JSON permits exactly one same-actor format correction, preserving
evidence/conclusions. Schema/citation errors are terminal. Both attempts remain
in authenticated history; replay requires adjacent correction after the invalid
attempt and rejects duplicate valid results or exhausted correction. Explicit
`--max-turns` still limits the whole panel.

Host `select_agent` enforces order and `finish` validates without another model
call. Captured `turn_committed` events must match final history. Completion
requires strict outcome, correct route, result fields and attributed assessments;
engine finalization or agent names in prose alone are insufficient. For docs,
the actual last verifier turn must end with accepted `DOCS_AUDIT` and Chair must
set `audited=true`; Chair cannot overrule a veto. Fresh guide reuse skips that
panel and discloses unaudited semantics through preflight context.

Panels share a cooperative elapsed budget across agents/tools/retries; late
outcomes and pending tools cannot publish. Native calls/waits can overrun. Read [provider observation](../topics/provider-observation.md) when
changing retry behavior, request accounting, progress, budgets or diagnostics.

Default output omits discussion/JSON; verbosity adds exchanges. Explicit
transcripts use direct delivery, so errors stop review instead of being
suppressed by kerness fan-out. Diagnostics preserve safe error categories and
HTTP/timeout detail, excluding endpoints/raw causes/bodies. A committed turn
is not panel completion.

## Dependencies and Boundaries

[Workflow](review-cli.md) builds topics and supplies source/guide/provider;
[Reports](reporting.md) validates schemas, assembles evidence and gates approval.
Read both for stage/result/context changes. [Preflight](architecture-preflight.md)
owns docs content and generated paths; read it for docs schema/access changes.
Consult [Git](git-io.md)/[GitHub](github-io.md) only for transport/service-tool
changes, and [Prompts](prompts.md) for rubric/profile changes. Runtime and
construction depend on the provider observer; it imports neither owner nor CLI.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| -------------- | ---------------- | ---------------------- |
| Routing/record formats | Roster, host/replay, gameplans, validators; scripted sessions | Reports and Workflow; inspect actual delivered messages |
| Docs phases/acceptance | `PHASES`, docs gameplan and final verifier gate | Preflight; independent veto/strict rotation cases |
| Tool/guide boundary | Registry, gameplan lists, `_build`; access regressions | Git/GitHub or Preflight for affected boundary |
| Provider/API/dependency | Observer/construction and patched binding | Triggered provider/dependency topic; root suite/selfcheck |

## Verification

Run [root checks](../../ARCHITECTURE.md#verification) from repository root.
`tests/test_workflow.py` uses real scripted sessions to prove consultants,
conditional verification, actual prompt delivery, attribution/finding accounting,
dissent, strict errors, result correction/history, malformed/duplicate records,
turn budgets, tool confinement, docs vetoes and transcript success/failure.
Provider and elapsed-time cases are mapped in the provider topic; binding
changes require the dependency topic's additional checks. Expect unittest `OK`
and selfcheck success, exit 0. No external model/GitHub request occurs.

## Known Gaps

Identity is enforced, semantic understanding is model-dependent. Imported libraries retain caller signal behavior; CLI termination belongs to
Workflow. Provider/topic gaps cover elapsed and synchronous-wait limits. No new
runtime/concurrency milestone is accepted.
