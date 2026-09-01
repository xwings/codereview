# git-io (git_io.py)

## Goal

Manages the script-owned local clone of the repo under review (default
`./repo/<name>`, gitignored): first-run clone, origin verification,
dirty-tree guard, base-branch reset, and the fresh `review/pr-<n>-<sha>`
checkout that PR reviews run against. The checkout exists so the LLM gets
full file context, not just diff hunks. Infrastructure.

## Status

`done` — implements hard guardrails #2 (fresh branch) and #6 (no pushes);
the How to Test commands pass.

## Code Structure

| File | Role |
| ---- | ---- |
| `git_io.py` | `git()` wrapper (deny-list checked), clone lifecycle, branch management |

## Key Types and Entry Points

- `git_io.py:11` - `git(*args, cwd, check)` - the one `git` runner; every call passes the shared deny-list (`git push` forbidden), non-zero exit becomes a clean `SystemExit`.
- `git_io.py:29` - `ensure_clone(workdir, repo)` - clones on first run; on reuse verifies `git remote get-url origin` matches `https://github.com/<repo>.git` and refuses a same-named clone of a different repo (e.g. a fork via `--repo`, or two repos that share a name).
- `git_io.py:49` - `assert_clone_clean(clone)` - refuses to start when the clone has uncommitted changes (guardrail #2's dirty-tree half); tells the user how to reset.
- `git_io.py:58` - `reset_to_branch(clone, branch)` - `fetch` + `checkout` + `reset --hard origin/<branch>`. The branch comes from `resolve_base_branch` — see below.
- `git_io.py:65` - `checkout_pr(clone, repo, n, short_sha)` - deletes any stale `review/pr-<n>-*` branches (force-pushes change the sha), then `gh pr checkout -b review/pr-<n>-<sha>`.

### Base-branch resolution, and why a profile may pin one

`review.py:177` - `resolve_base_branch(repo, profile, override, pr_base)` takes
the first of:

| | order |
| - | ----- |
| PR | `--base-branch` → the PR's own `baseRefName` → the profile's pin → the repo's GitHub default |
| Issue | `--base-branch` → the profile's pin → the repo's GitHub default |

The GitHub lookup (`github_io.fetch_default_branch`, a read-only `gh repo
view`) is **last and lazy**: a repo answered by an earlier source costs no
extra call.

The profile pin exists for one situation: a project whose real working branch
is **not** what GitHub reports as its default. Projects that develop on a
`dev`, `main-dev` or `next` branch while their nominal default sits stale are
common enough, and `gh repo view` will confidently report the stale one. Such a
project sets `base_branch` in its `profile.json`, which is what issue triage
resets to; PR review is already covered by the PR's own `baseRefName`.

Any repo whose working branch *is* its GitHub default needs no pin. That is the
common case, and it is why the base branch cannot be hard-coded in Python: the
tool ships no profile at all, so a wired-in default would be wrong for every
repo that does not happen to share it, and the checkout would simply fail
against a branch that does not exist.

## Interactions

- Called by [review-cli.md](review-cli.md) (`handle_pr`, `handle_issue`) to prepare the checkout before the backend runs.
- Uses [github-io.md](github-io.md) for `gh pr checkout` and shares its deny-list machinery.
- The resulting checkout is the workspace the panel's `AccessPolicy` is scoped to — see [harness.md](harness.md).

## How to Test

```sh
python3 -m py_compile git_io.py       # pass = exit 0
python3 - <<'EOF'                     # pass = "ok push blocked"
from git_io import git
from github_io import ForbiddenCommand
try:
    git("push", "origin", "main"); print("FAIL push ran")
except ForbiddenCommand:
    print("ok push blocked")
EOF
.venv/bin/python - <<'EOF'            # pass = "ok base precedence"
import json, tempfile
from pathlib import Path
import github_io, review
# No profile ships, so the pinned case builds its own; `d` is the real fallback.
tmp = Path(tempfile.mkdtemp())
(tmp / "profile.json").write_text(json.dumps({"base_branch": "dev"}))
p = review.resolve_profile("any/repo", tmp)
d = review.resolve_profile("any/repo", None)
assert d == review.DEFAULT_PROFILE_DIR       # nothing under prompts/repos/ claims it
github_io.fetch_default_branch = lambda r: (_ for _ in ()).throw(AssertionError("gh called"))
assert review.resolve_base_branch("x/y", p, None, None) == "dev"           # profile pin
assert review.resolve_base_branch("x/y", p, None, "release") == "release"  # PR base wins
assert review.resolve_base_branch("x/y", p, "mine", "release") == "mine"   # flag wins
github_io.fetch_default_branch = lambda r: "main"
assert review.resolve_base_branch("x/y", d, None, None) == "main"          # gh, lazily
print("ok base precedence")
EOF
```

## Open Gaps / Roadmap

- The clone grows unbounded history over time; no pruning/GC is performed (acceptable for v1).
- `--workdir` holds one clone per repo *name*, not per `owner/name`. Two repos
  sharing a name cannot share a workdir; `ensure_clone` detects the collision
  from the origin URL and refuses rather than resetting the wrong tree, so the
  failure is safe — the user picks a different `--workdir`.
