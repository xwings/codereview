# prompts (prompts/)

## Goal

The reference material the panel reads, tunable without touching Python. Since
the harness moved to kerness, the *instructions* live in `gameplans/` and
`personas/` ([harness.md](harness.md)); what remains here is knowledge —
factual, evaluative, and per-language — organised **per repository**, because
the seven checks are universal but what a project considers correct is not.
Infrastructure.

## Status

`done` — a generic fallback profile and a shared style file, with `repos/`
deliberately empty; the How to Test commands pass.

## Code Structure

| File | Role |
| ---- | ---- |
| `prompts/coding_styles.md` | Check 1's ground truth: indentation and idiom per language. Shared by every repo. |
| `prompts/default/design.md` | EVALUATIVE fallback: project-agnostic rubric, severity vocabulary, approve threshold |
| `prompts/default/ARCHITECTURE.md` | FACTUAL fallback: tells the panel no curated map exists and how to build one from the tree |
| `prompts/default/profile.json` | `{}` — no base-branch pin |
| `prompts/repos/README.md` | The per-repo layout and what belongs in each file. No profile ships. |

**`prompts/repos/` is empty on purpose.** Every review starts from
`prompts/default/` until a maintainer writes a profile, so the fallback is the
common path rather than the exceptional one, and it is exercised by every run
instead of only by unfamiliar repos. A shipped profile would also make one
project's rubric the de facto default the moment anyone copied it.

`prompts/pr_review.md` and `prompts/issue_triage.md` are **deleted** — the
`{{PLACEHOLDER}}` templates they held are superseded by the gameplans and the
topic builders in `review.py`.

## Key Types and Entry Points

- `review.py:142` - `resolve_profile(repo, override)` - `--prompts DIR` if
  given (a non-directory is a clean exit), else
  `prompts/repos/<owner>/<name>/`, else `prompts/default/`. The selection is
  printed to stderr (`review.py:516`, `main`) so a run on the generic rubric is
  never silently mistaken for a curated one.
- `review.py:189` - `_read_prompt(profile, name, required)` - searches
  **profile → `prompts/default/` → `prompts/`** and takes the first hit. So a
  profile carries only what it wants to say: `coding_styles.md` stays shared at
  the root unless a project overrides it, and `default/` backstops anything a
  profile omits. A missing `ARCHITECTURE.md` degrades to a placeholder; a
  missing `design.md` or `coding_styles.md` is a hard, clean exit — losing the
  rubric would mean reviewing with no severity vocabulary at all.
- `review.py:243` - `build_pr_topic(...)` loads all three from the resolved
  profile, in this order: architecture → rubric → style reference → measured
  facts → the case. `build_issue_topic` (review.py:286) loads only the
  architecture layer.
- `review.py:157` - `profile_base_branch(profile)` - reads the optional
  `base_branch` from `profile.json`; see [git-io.md](git-io.md) for where it
  sits in the precedence chain.
- The severity vocabulary (`blocker` / `major` / `nit` / `info`) and the approve
  threshold live in whichever `design.md` is in force and **only** there.
  Personas reference them; they do not restate them, so there is one place to
  tune strictness — and every profile's `design.md` must define both, because
  `downgrade_if_needed` (review.py:357) acts on them.
- `coding_styles.md` carries one overriding rule: **the repository beats this
  file.** Where a file consistently does something else, matching its
  neighbours is correct. It also names what CI already owns (line length,
  import order, trailing whitespace) so the panel does not spend the
  contributor's attention on it. `prompts/default/design.md` repeats that rule
  for judgment, which matters far more without a curated architecture doc: a
  rule the panel cannot point at a file for is not a rule.
- `coding_styles.md` describes the four core languages — Python, C, C++,
  Rust — plus `.asm`, `.sh`, `.yml`, `.toml` and `.md`. That set is deliberately
  the one `repo_facts.INDENT_LANGS` measures ([review-cli.md](review-cli.md)):
  a language the file described but the tool could not measure would have
  check 1 asserting a convention with no repo baseline to point at, which is
  exactly what the overriding rule forbids. Adding a language means editing
  both, in the same change.
- `profile.json` carries `base_branch` and nothing else — for a project whose
  real working branch is not its GitHub default. See [git-io.md](git-io.md).

### Onboarding a new repo

Create `prompts/repos/<owner>/<name>/` and write `design.md`. Optionally add
`ARCHITECTURE.md` (a factual map of the project), `coding_styles.md` (only if
the project's languages differ from the shared file), and `profile.json` (only
if the working branch is not the GitHub default). No Python changes.
`prompts/repos/README.md` is the reference; `prompts/default/` is the template
to copy from.

Skipping this is supported, not broken: the repo gets `prompts/default/`, which
is a real rubric rather than a stub. The trade is that the panel spends its
`study_repo` phase deriving the project's structure instead of being handed it.

## Interactions

- Loaded by [review-cli.md](review-cli.md) into the session topic.
- Consumed by the panel described in [harness.md](harness.md).
- The factual/evaluative/style split is deliberate: a project's structure, the
  maintainer's judgment, and per-language convention change for different
  reasons and at different rates. The per-repo/shared split is the same
  argument one level up.

## How to Test

```sh
ls prompts/coding_styles.md prompts/default/design.md \
   prompts/default/ARCHITECTURE.md prompts/default/profile.json \
   prompts/repos/README.md                             # pass = all listed
test ! -e prompts/pr_review.md && test ! -e prompts/issue_triage.md && echo "ok templates retired"
grep -rn '{{' prompts/ ; test $? -eq 1 && echo "ok no stale placeholders"
# pass = "ok repos/ ships no profile" — a shipped profile would become the de
# facto default the moment anyone copied it, and would name a project the tool
# has no business preferring.
test -z "$(find prompts/repos -mindepth 1 -type d)" && echo "ok repos/ ships no profile"
.venv/bin/python -c "import json; assert json.load(open('prompts/default/profile.json')) == {}; \
  print('ok default profile pins no branch')"
# pass = no FAIL. `find`, not a glob: prompts/repos/ is empty, and an unmatched
# glob is an error in zsh rather than a literal.
find prompts -name design.md | while read -r f; do
  grep -q 'verdict = "approve"' "$f" || echo "FAIL no approve threshold in $f"
done; echo "ok every rubric defines the approve threshold"
.venv/bin/python - <<'EOF'   # pass = "ok styles cover every measured language"
import re
from repo_facts import INDENT_LANGS
doc = open("prompts/coding_styles.md").read()
listed = set(re.findall(r"`(\.\w+)`", doc))
missing = sorted(set(INDENT_LANGS) - listed)
print("FAIL not in coding_styles.md:", missing) if missing else \
    print("ok styles cover every measured language")
EOF
```

## Open Gaps / Roadmap

- Every `ARCHITECTURE.md` is a manual snapshot; nothing keeps one in sync as
  its project evolves.
- A PR in a language `coding_styles.md` does not list gets the "repository
  beats this file" fallback and nothing more. A project outside the four core
  languages therefore wants its own `coding_styles.md` in its profile, and
  nothing prompts the maintainer to write one — the run is announced as
  `generic` but not as *styleless*.
- No repo profile ships, so the generic rubric is what every review actually
  uses and nothing demonstrates a filled-in profile end to end;
  `prompts/repos/README.md` describes one but no test exercises the curated
  path. It also still encodes one maintainer's priorities; revisit the
  thresholds as review experience accumulates across projects.
