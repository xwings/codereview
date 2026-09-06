# Review panels and runtime

## Goal

Provide M1's architecture preparation, PR review and issue investigation panels.
Gameplans define the phases and result contracts; personas supply distinct
professional responsibilities; the runtime verifies completion and attributes
merge ballots before the CLI may publish a result.

## Status

`done` — all three panel contracts and strict completion/vote gates pass the
23-case workflow suite. All 502 upstream Python binding tests, Rust tests,
clippy and kerness selfcheck pass with the PyO3 compatibility patch.

## Code Structure

| File | Role |
| ---- | ---- |
| `session_builder.py` | Provider, workspace, registered agents and tools for each panel |
| `panel_runtime.py` | Rosters, display names, compact output, strict run outcomes and ballot attribution |
| `gameplans/pr_review.md` | Seven reviewers, five phases and PR result contract |
| `gameplans/issue_triage.md` | Two investigators, three phases and issue result contract |
| `gameplans/architecture_docs.md` | Planner, writer and verifier producing proposed architecture documents |
| `personas/*.md` | Specific expertise and boundaries for reviewers, investigators, documentation agents and chair |
| `agent_tools.py` | Tracked-file search, PyPI advisory/metadata lookup and GitHub upstream metadata |
| `patches/kerness-pyo3.patch` | Reproducible PyO3 security update against the pinned public kerness source |

## Key Types and Entry Points

- `session_builder.py:29` — `build_provider` constructs an OpenAI-compatible
  endpoint without persisting its key.
- `session_builder.py:38` — `_build` confines source reads to the original
  working tree, grants individual prepared documentation files, binds a panel
  and disables persistent session state and inter-turn delays.
- `session_builder.py:101` — `build_pr_session`; issue and documentation
  builders select their corresponding gameplans and rosters below it.
- `panel_runtime.py:12` — `PANELS` holds stable routing IDs and persona files;
  `PHASES` and `TITLES` define the runtime contract and human display names.
- `panel_runtime.py:55` — `PanelChannel` prints concise progress on stderr;
  verbose output and an optional complete transcript preserve detailed turns.
- `panel_runtime.py:98` — `PanelResult` carries strict fields, authenticated
  history, phase counters, usage and separately attributed votes.
- `panel_runtime.py:137` — `validate_panel` requires every phase and every
  participant turn, then parses each specialist's own final ballot.
- `panel_runtime.py:187` — `run_session` drives the owned kerness run with
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

Documentation preparation also requires the actual final DocsVerifier turn to
end with `DOCS_AUDIT {"accepted":true,"reason":"Source evidence checked."}`.
The runtime rejects a missing, malformed or negative record, and requires the
chair's `audited` field to be true as well. The chair cannot overrule an
independent documentation rejection.

Output does not repeat chair chatter and raw JSON by default. The optional raw
transcript is delivered directly so a write failure stops the run; kerness's
fan-out channel intentionally suppresses member failures and therefore is not
suitable for this required audit artifact. Transcript destinations are declared
to the same access policy as the checkout.

When prepared documents live in a separate worktree, only its root
`ARCHITECTURE.md` and direct `ARCHITECTURE/*.md` files receive additional read
grants. Other files in that worktree remain inaccessible. Source reads and
searches continue against the original Git checkout, preserving reviewed
documentation changes and their line numbers.

No gameplan declares commands, writes, or executable skills. Kerness narrows
registered tools to each gameplan's list. Built-in file/directory reads enforce
the workspace; `repo_grep` is a fixed Git search with an option-separated pattern
and optional pathspec. The package tool supplies PyPI/OSV evidence; GitHub
metadata does not establish advisories for arbitrary package ecosystems.

## Interactions

- [review-cli.md](review-cli.md) builds topics, runs panels, validates source
  citations and renders/publishes the final result.
- [prompts.md](prompts.md) supplies supplementary repository profiles and rubrics.
- [git-io.md](git-io.md) prepares isolated source and documentation worktrees.
- [github-io.md](github-io.md) confines GitHub interactions to audited commands.
- Architecture preparation calls the documentation panel for proposed markdown;
  the host validates and materializes it, while model tools remain read-only.

## How to Test

From the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m kerness.selfcheck
.venv/bin/python -m pytest vendor/kerness/bindings/python/tests -q
cargo test --manifest-path vendor/kerness/Cargo.toml -p kerness --locked
cargo clippy --manifest-path vendor/kerness/Cargo.toml --workspace --all-targets --locked -- -D warnings
```

The workflow suite must exit zero and exercise actual scripted panel rounds,
strict result errors, per-agent ballot attribution, dissent, early termination,
compact output and transcript delivery. Kerness selfcheck must print
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

## Open Gaps / Roadmap

- Participation and ballot identity are enforced; semantic understanding of
  every source read and the quality of debate cannot be proved from prose.
  Source citations, cross-examination and maintainer review remain necessary.
- Every PR requires 35 specialist turns plus chair routing and two closing
  passes. `--max-turns` can limit cost, but an exhausted run cannot publish.
- Package advisory coverage is PyPI-specific; other ecosystems need additional
  evidence and must not be reported as verified when evidence is absent.
- Model calls are synchronous. Progress reports completed turns; cancellation
  cannot forcibly interrupt a blocked provider call.
