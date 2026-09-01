# No curated architecture reference for this repository

This project has no profile under `prompts/repos/<owner>/<name>/`, so nobody has
written down its layering, its public API surface, or its internal boundaries
for you. You are reading the fallback.

**Do not invent a structure.** The `study_repo` phase exists precisely for this
case: build the map yourself, from the tree, before you look at the diff.

In your own area only, and using `list_dir`, `read_file` and `repo_grep`:

- Read the top-level `README`, and any `CONTRIBUTING`, `ARCHITECTURE`,
  `CLAUDE.md`/`AGENT.md`, or `docs/` file that describes intent. A project that
  states its own rules outranks anything you would infer.
- List the top level and the top two levels of the main source directory. Name
  the modules and what each appears to own.
- Find the public entry point — the package `__init__`, the exported surface,
  the CLI, the main header. What a caller outside the project can touch is what
  a change can break.
- Read the dependency manifest (`requirements.txt`, `pyproject.toml`,
  `package.json`, `Cargo.toml`, `go.mod`, …). It tells you what the project has
  already decided to depend on, which is the baseline for check 6.
- Look at the linter/formatter/CI configuration. What CI already enforces, you
  do not need to.

Report what you found as concrete observations with file paths, and say plainly
where you could not establish a baseline. An area with no settled convention is
itself a finding, and it limits what you may demand of this pull request: you
cannot hold a contributor to a rule that nothing in the tree demonstrates.

To give a project a real architecture reference instead of this one, add
`prompts/repos/<owner>/<name>/ARCHITECTURE.md`. No code change is needed.
