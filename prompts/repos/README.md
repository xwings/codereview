# Repo profiles

Per-project knowledge, looked up by `--repo`. Empty by design: the tool ships
no profile, so every repository is reviewed against `../default/` until someone
writes one here.

## Layout

```
repos/<owner>/<name>/
├── ARCHITECTURE.md     optional — a factual map of the project
├── design.md           optional — the maintainer's rubric
└── coding_styles.md    optional — only if the project's languages differ
```

Every file is optional. Lookup falls through **profile → `../default/` →
`../`**, so a profile carries only what it wants to say and `../default/`
backstops the rest. Creating a directory here needs no Python change.

## What to put in each

- **`ARCHITECTURE.md`** — layering, module ownership, the public API surface,
  the invariants a contributor is expected to know. These are supplementary
  notes; the prepared guide and selected or merged source take precedence.
  The selected source's entire architecture set must pass version, layout,
  size and navigation checks; profile notes cannot bypass preparation. Keep
  notes concise so they do not undo the prepared guide's task-based reading.
- **`design.md`** — what *this* maintainer considers a blocker. It must define
  the severity vocabulary and the approve threshold; `../default/design.md`
  is the template. `reporting.validate_pr` always enforces unanimous merge
  recommendations from Lead and Verifier, justified need and no unresolved
  questions or major/blocker findings.
- **`coding_styles.md`** — only when the project's languages fall outside the
  four the shared file covers (Python, C, C++, Rust). Overriding it replaces
  the whole file, not one section.

Branch selection is required through `--branch`; profiles contain Markdown
knowledge only. `--branch` replaces the former `--base-branch` option and JSON
branch pins. For example, select `--branch dev` to review against development
source even when the GitHub default is `main`.

## The rule every profile inherits

The repository is the source of truth. A profile describes what is already
visible in the tree; it does not legislate. A convention the panel cannot point
at a file for is not a convention, and nothing may be demanded on its
authority.

See [ARCHITECTURE/modules/prompts.md](../../ARCHITECTURE/modules/prompts.md).
