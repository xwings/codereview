# github-io (github_io.py)

## Goal

The single chokepoint for every GitHub interaction. Per hard guardrail #1,
all reads and writes shell out to the `gh` CLI — no REST/GraphQL, no Python
GitHub packages — so the maintainer's existing `gh auth login` is reused and
the deny-list has exactly one enforcement point. Infrastructure.

## Status

`done` — deny-list blocks the known bypass forms; the How to Test commands pass.

## Code Structure

| File | Role |
| ---- | ---- |
| `github_io.py` | `gh()` wrapper, deny-list (`_check_prefix`), auth preflight, fetch/post helpers |

## Key Types and Entry Points

- `github_io.py:14` - `FORBIDDEN_GH_PREFIXES` - `pr merge`, `pr close`, `issue close`, `api` (raw API could merge/close/push), `repo sync` (performs a push).
- `github_io.py:21` - `FORBIDDEN_GIT_PREFIXES` - `push` (shared with [git-io.md](git-io.md)).
- `github_io.py:33` - `_check_prefix(args, forbidden, tool)` - skips leading option tokens (consuming values of `-C`, `-c`, `-R/--repo`, …) before prefix-matching, so `git -C <dir> push` is still caught. Raises `ForbiddenCommand` (github_io.py:29).
- `github_io.py:48` - `gh(*args, cwd, check)` - the one `gh` runner; deny-list checked first, non-zero exit becomes a clean `SystemExit` with stderr.
- `github_io.py:66` - `ensure_gh_ready()` - exit 2 if `gh` is missing or unauthenticated, before anything else runs.
- `github_io.py:78` - `fetch_default_branch(repo)` - `gh repo view --json defaultBranchRef`; the last resort in base-branch resolution ([git-io.md](git-io.md)), called only when neither the PR nor the repo's profile names a branch. A repo that reports none is a clean exit pointing at `--base-branch`, not a silent guess.
- `github_io.py:91` - `fetch_pr(repo, n)` - `gh pr view --json` (title, body, author, `baseRefName`, `headRefOid`, files, …).
- `github_io.py:100` - `fetch_pr_diff(repo, n)` / `github_io.py:105` - `fetch_issue(repo, n)`.
- `github_io.py:111` - `post_pr_review(repo, n, approve, body)` - `gh pr review --approve|--comment`; `github_io.py:116` - `post_issue_comment(...)`.

Every one of these takes `repo` as a canonical `owner/name`. `--repo` is
normalized and validated once, at the CLI boundary (`review.py:48`,
`normalize_repo`), before it can reach an argv or a filesystem path — see
[review-cli.md](review-cli.md).

### Reads the panel can trigger

`agent_tools.make_github_repo_health` ([harness.md](harness.md)) calls
`gh repo view <repo> --json …` through this same wrapper with `check=False`, so
a dependency lookup an agent asks for is subject to the deny-list like anything
else. It is a read of an arbitrary third-party repository — the only place
where PR content chooses a `gh` argument — which is why it validates the
`owner/name` shape itself and why the deny-list, not the caller, is what makes
that safe.

Advisories deliberately do *not* come from `gh api` (deny-listed, see below);
`package_health` queries OSV.dev over stdlib `urllib` instead, which covers
GHSA.

## Interactions

- Called by [review-cli.md](review-cli.md) for all fetches and posts.
- Called by [git-io.md](git-io.md) for `gh pr checkout` (and lends it the deny-list machinery for `git`).
- Called by [harness.md](harness.md) for the `github_repo_health` tool.

## How to Test

```sh
python3 -m py_compile github_io.py    # pass = exit 0
python3 - <<'EOF'                     # pass = five "ok blocked" lines, no FAIL
from github_io import ForbiddenCommand, _check_prefix, FORBIDDEN_GH_PREFIXES, FORBIDDEN_GIT_PREFIXES
for args, fb, tool in [
    (("-C","x","push"), FORBIDDEN_GIT_PREFIXES, "git"),
    (("push","origin"), FORBIDDEN_GIT_PREFIXES, "git"),
    (("api","-X","PUT","repos/o/r/pulls/1/merge"), FORBIDDEN_GH_PREFIXES, "gh"),
    (("pr","merge","1"), FORBIDDEN_GH_PREFIXES, "gh"),
    (("repo","sync"), FORBIDDEN_GH_PREFIXES, "gh"),
]:
    try:
        _check_prefix(args, fb, tool); print("FAIL", args)
    except ForbiddenCommand:
        print("ok blocked", args)
EOF
```

## Open Gaps / Roadmap

- The deny-list guards the `gh()`/`git()` wrappers only; a contributor calling `subprocess` directly bypasses it. That is a convention enforced by review, not code.
- Blocking `gh api` entirely is deliberately coarse — it also blocks harmless reads, which is why GHSA advisories are fetched from OSV instead. Loosen to method-aware filtering only if a read-only `gh api` call is ever actually needed.
