# Generic Review Rubric

> This project has no profile under `prompts/repos/<owner>/<name>/`, so this is
> the project-agnostic fallback. It defines the severity vocabulary and the
> approve threshold — those are fixed, the tool depends on them — and gives
> general guidance on what to flag.
>
> To tune review behavior for a specific project, add
> `prompts/repos/<owner>/<name>/design.md`. No code changes needed.

**The overriding rule: the repository beats this file.** Everything below is a
general prior. The baseline you established in the `study_repo` phase is the
evidence. Where the two disagree, the repository wins, and a rule you cannot
point at a file for is not a rule — you may not demand it of a contributor.

## What to flag

### Need and fit with the project

Check whether the change is needed before judging its implementation. Establish
the concrete user or maintainer problem and the evidence for it: what remains
broken, missing, or unnecessarily difficult without this PR? Then check whether
existing functionality, configuration, or documentation already covers the
actual use case, whether the solution belongs in this project and layer or in
an extension/downstream application, and whether the benefit warrants the API,
complexity, dependencies, and maintenance it adds. Consider a smaller solution
that achieves the same benefit.

Use the project's stated purpose, documented direction, and source as evidence;
do not impose personal product preferences or assume a new capability is out
of scope simply because it is new. Concrete maintenance, documentation,
accessibility, and bug-fix improvements are valid benefits. Neither a ticket
nor a benchmark is required for every change. An existing alternative must
cover the actual use case and exist independently of this PR before it
establishes that an addition is redundant; the checkout includes the PR's code.

Record one conclusion in the Fit checklist note, with its evidence or reason:

- **Need: justified** — a concrete benefit warrants the change; still assess
  placement and proportionality before passing the whole Fit check.
- **Need: unclear** — the available context does not establish the need; name
  what is missing and use checklist status `concern` unless a separate
  confirmed Fit blocker applies. Uncertainty alone is neither a code finding
  nor a blocker; do not invent a file, line, or fix for it.
- **Need: unnecessary** — positive evidence shows the change adds no needed
  benefit, such as an existing API already covering the same use case. Use
  checklist status `concern` unless a separate confirmed blocker applies.
  A code finding requires real `file:line` evidence and an actionable remedy,
  such as removal or reuse, in the existing finding fields. Assign its severity
  by the demonstrated impact using this rubric; the conclusion alone does not
  imply a blocker.

Missing justification is not evidence that a PR is unnecessary. Both unclear
and unnecessary need require `verdict = "comment"`, even with no code findings.

### Layering & boundaries

Derive the project's boundaries from the tree, then judge against them:

- A change that reaches across a boundary the project otherwise maintains —
  a module poking another module's internals instead of using its public
  surface — **major**. Cite both the crossing and an existing call site that
  does it the intended way.
- A layer taking on work that belongs to another (parsing code doing policy,
  presentation code doing persistence) — **major**.
- A change touching several unrelated subsystems in one pull request with no
  stated reason — call it out for split-up.

### Public API impact

- Renaming, removing, or changing the signature of anything the project exports
  to its callers — **blocker** unless the pull request explicitly justifies it
  and the project is pre-1.0 or documents the break.
- Changing the *meaning* of an existing exported function or field while
  keeping its signature — **blocker**. This is the break that CI does not catch.
- Adding a new public entry point that overlaps an existing one — **major**
  (consolidate).

### Correctness & quality signals

- `print` / `console.log` / `println!` in library code where the project has a
  logger — **major**. Confirm the logger exists before flagging.
- Exception handling that swallows silently — a bare `except:`, `except
  Exception: pass`, an ignored error return, a discarded `Result` — **major**.
- Magic numbers for protocol constants, sizes, offsets, or limits, where the
  project names such constants elsewhere — **nit** to **major** by scope.
- Hard-coded absolute paths, hostnames, ports, or credentials — **major**;
  a credential is a **blocker**.
- Resources acquired without a guaranteed release on every path, including
  error paths — **major**.
- Copy-pasted blocks that should share a helper — **major**. Quote both sites.
- A new top-level dependency without justification — **major**. Weigh it
  against what the manifest already pulls in and against the standard library.
- Missing or misleading type annotations on new public functions, in a project
  that annotates — **nit**.
- Large committed binaries or fixtures without a clear reason — **major**.
- Dead code, commented-out code, and filler comments that restate the line
  below them — **nit**, or **major** if the pull request is mostly this.

## What NOT to flag

- Missing tests, by themselves. CI runs the suite; absence of tests is at most
  an **info** observation, never a blocker.
- Missing changelog or documentation updates unless the change is clearly
  user-facing.
- Style preferences the project's own linter would catch — line length, import
  order, trailing whitespace. Let CI handle it.
- Whitespace, EOL, or pure-formatting diffs.
- Any convention you cannot demonstrate from the tree.

## Severity guidance

- **blocker** — public-API break, security regression, data corruption, or a
  boundary violation that is hard to undo.
- **major** — clear bug, boundary violation, or significant drift from the
  project's own established practice that should be fixed before merge.
- **nit** — small style or naming issue.
- **info** — observation worth raising but not a problem.

## Approve threshold

Use `verdict = "approve"` ONLY if:

- Zero `blocker` findings, AND
- Zero `major` findings, AND
- The pull request is not a draft, AND
- The pull request description (or commits) make the intent clear, AND
- Fit established `Need: justified` in verify and recorded the evidence in its
  checklist note.

Otherwise, use `verdict = "comment"`.
