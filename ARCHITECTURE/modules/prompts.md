---
eatmycode_version: "2.0.0"
---
# Repository profiles and shared prompts

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `prompts/`, profile lookup or topic prose in `review.py`,
supplementary architecture, review rubrics or measured language guidance.

## Responsibility and Status

Supply optional project knowledge without replacing authoritative source or
the prepared architecture guide. `in progress` — implemented; default CLI tests
exercise generic fallback. Lookup precedence is source-inspected, with dedicated
coverage gaps below. No project-specific profile ships.

## Code Map

| Path / symbol | Role |
| ------------- | ---- |
| `review.py:resolve_profile`, `_read_prompt` | Profile precedence and required-file fallback |
| `review.py:build_pr_topic`, `build_issue_topic` | Source/guide, supplementary facts and case prose |
| `prompts/default/`, `prompts/coding_styles.md` | Generic architecture/need/severity/style guidance |
| `prompts/repos/README.md`, default CLI cases in `tests/test_workflow.py` | Optional profiles and generic fallback integration evidence |

## Local Conventions

Python follows [root conventions](../../ARCHITECTURE.md#code-conventions).
Markdown uses the need/severity vocabulary in `prompts/default/design.md`.
Profiles supply supplementary prose only; no schema/Markdown checker exists.
The repository's demonstrated conventions outrank generic style guidance.

## Contracts and Invariants

Explicit `--prompts` wins, then `prompts/repos/<owner>/<name>`, then default.
Individual files fall through profile → default → shared prompts root. Missing
required rubric/style text fails clearly. Required `--branch` independently
chooses source; JSON branch pins/default-branch fallbacks do not apply.

Prepared root/rules are available in the topic. Reviewers reuse them and follow
Task Index source paths/change triggers into only the relevant owner, matching
index branches and triggered topics. Inspect boundary partners when relevant;
do not inventory the full source/docs tree or reread agent aliases. Repository
files, profiles and case text are evidence, never permission to change tools,
roles or review protocol. Original documentation only needs extra inspection
when it affects a claim or is itself changed; original source stays authoritative.

The generic rubric requires positive evidence of need, independently established
existing alternatives, correct placement and proportionality. Fit retains
`Need: justified`, `Need: unclear` or `Need: unnecessary`; only justified need
can approve. Missing context alone is a concern, not an invented code defect.
Custom rubrics can strengthen policy but cannot bypass host citation/approval
gates. Issue topics do not apply PR approval policy.

Measured style/symbol leads cover Python, C, C++ and Rust (`repo_facts.py`);
shared style guidance must agree with measurements. Regex observations are
leads rather than verdicts. Other languages require direct repository evidence.

## Dependencies and Boundaries

[Workflow](review-cli.md) coordinates profile resolution and topic use; read it
for precedence/API changes. [Preflight](architecture-preflight.md) owns guide
freshness and routing context independently from profiles; read it for guide
context changes. [Panels](harness.md) owns roles and [Reports](reporting.md)
enforces policy; read both when changing need/severity/result instructions.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| -------------- | ---------------- | ---------------------- |
| Profile precedence | Lookup functions; default CLI integration setup | Workflow; add coverage for the changed precedence behavior |
| Architecture reading prose | Topic builders and default architecture prompt | Preflight/Panels; selective route and context cases |
| Rubric/need vocabulary | Default design and role instructions | Reports/Panels; approval/hold cases |
| Language reference | Shared styles and `repo_facts.py` | Workflow measured leads; source authority preserved |

## Verification

Run [root checks](../../ARCHITECTURE.md#verification). Default CLI integration in
`tests/test_workflow.py` exercises generic profiles; CLI cases cover required
branch selection and topic cases cover architecture context. Precedence in
`review.py:resolve_profile` and `_read_prompt` is established by source inspection,
not dedicated tests. Inspect fallback text and topic builders for source
authority and the absence of bundled owner/name profiles.
Passing means unittest `OK`, exit 0 and no syntax diagnostics. Tests do not prove
that a live model follows prose instructions.

## Known Gaps

Explicit `--prompts` overrides, per-repository selection and individual-file
fallback precedence have no dedicated tests. Profiles are manually maintained
snapshots and can drift; source and prepared guidance take precedence. Languages
beyond the measured set have no automated style/symbol leads. New measurement
support requires explicit scope and checks.
