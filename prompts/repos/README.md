# Repo profiles

Per-project knowledge, looked up by `--repo`. Empty by design: the tool ships
no profile, so every repository is reviewed against `../default/` until someone
writes one here.

## Layout

```
repos/<owner>/<name>/
├── ARCHITECTURE.md     optional — a factual map of the project
├── design.md           optional — the maintainer's rubric
├── coding_styles.md    optional — only if the project's languages differ
└── profile.json        optional — {"base_branch": "..."}
```

Every file is optional. Lookup falls through **profile → `../default/` →
`../`**, so a profile carries only what it wants to say and `../default/`
backstops the rest. Creating a directory here needs no Python change.

## What to put in each

- **`ARCHITECTURE.md`** — layering, module ownership, the public API surface,
  the invariants a contributor is expected to know. This is what checks 3 and 5
  are measured against; without it the panel spends its `study_repo` phase
  deriving the structure from the tree instead of being handed it.
- **`design.md`** — what *this* maintainer considers a blocker. It must define
  the severity vocabulary and the approve threshold, because `review.py`'s
  `downgrade_if_needed` acts on them; `../default/design.md` is the template.
- **`coding_styles.md`** — only when the project's languages fall outside the
  four the shared file covers (Python, C, C++, Rust). Overriding it replaces
  the whole file, not one section.
- **`profile.json`** — `base_branch` only, and only when the project's working
  branch is not its GitHub default. A project developing on `dev` while its
  `master` sits stale needs this or it is reviewed against the stale branch.

## The rule every profile inherits

The repository is the source of truth. A profile describes what is already
visible in the tree; it does not legislate. A convention the panel cannot point
at a file for is not a convention, and nothing may be demanded on its
authority.

See [ARCHITECTURE/prompts.md](../../ARCHITECTURE/prompts.md).
