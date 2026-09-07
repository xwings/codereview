"""All GitHub interaction goes through `gh`. Single chokepoint for the deny-list."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Forbidden subcommand prefixes for `gh` and `git`. Checked before every
# subprocess call so guardrails 1, 4, 5, 6 cannot be silently broken.
FORBIDDEN_GH_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("pr", "merge"),
    ("pr", "close"),
    ("issue", "close"),
    ("api",),          # raw API access could merge/close/push
    ("repo", "sync"),  # performs a git push
)
FORBIDDEN_GIT_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("push",),
)

# Leading options that take a separate value argument (e.g. `git -C <dir> push`).
_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "-R", "--repo"}


class ForbiddenCommand(RuntimeError):
    pass


def _check_prefix(args: tuple[str, ...], forbidden: tuple[tuple[str, ...], ...], tool: str) -> None:
    # Skip leading option tokens so `git -C <dir> push` still matches ("push",).
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in _OPTIONS_WITH_VALUE else 1
    rest = args[i:]
    for prefix in forbidden:
        n = len(prefix)
        if len(rest) >= n and tuple(rest[:n]) == prefix:
            raise ForbiddenCommand(
                f"refusing to run `{tool} {' '.join(args)}` — "
                f"`{tool} {' '.join(prefix)}` is on the deny-list"
            )


def gh(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Single chokepoint for every `gh` invocation in the codebase."""
    _check_prefix(args, FORBIDDEN_GH_PREFIXES, "gh")
    res = subprocess.run(
        ["gh", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if check and res.returncode != 0:
        raise SystemExit(
            f"error: `gh {' '.join(args)}` failed (exit {res.returncode})\n"
            f"  stderr: {res.stderr.strip() or '(empty)'}\n"
            f"  stdout: {res.stdout.strip() or '(empty)'}"
        )
    return res


def ensure_gh_ready() -> None:
    if shutil.which("gh") is None:
        raise SystemExit(
            "error: `gh` CLI not found on PATH. Install from https://cli.github.com/"
        )
    res = gh("auth", "status", check=False)
    if res.returncode != 0:
        raise SystemExit(
            "error: `gh` is not authenticated. Run `gh auth login` first."
        )


def fetch_pr(repo: str, n: int) -> dict[str, Any]:
    fields = (
        "number,title,body,author,headRefOid,headRefName,baseRefName,"
        "files,additions,deletions,state,isDraft,url"
    )
    res = gh("pr", "view", str(n), "--repo", repo, "--json", fields)
    return json.loads(res.stdout)


def fetch_issue(repo: str, n: int) -> dict[str, Any]:
    fields = "number,title,body,author,comments,labels,state,url"
    res = gh("issue", "view", str(n), "--repo", repo, "--json", fields)
    return json.loads(res.stdout)


def detect_kind(repo: str, n: int) -> str:
    """Confirm the resource kind; a failed PR lookup alone is not an issue."""
    pr = gh("pr", "view", str(n), "--repo", repo, "--json", "number,url", check=False)
    if pr.returncode == 0:
        return "pr"
    issue = gh("issue", "view", str(n), "--repo", repo, "--json", "number,url", check=False)
    if issue.returncode == 0:
        # Some gh versions accept PR numbers through the issue endpoint.
        url = json.loads(issue.stdout).get("url", "")
        return "pr" if "/pull/" in url else "issue"
    raise SystemExit(
        f"error: cannot find PR or issue #{n} in {repo}. Nothing posted.\n"
        f"  PR lookup: {pr.stderr.strip()}\n  Issue lookup: {issue.stderr.strip()}"
    )


def post_pr_review(repo: str, n: int, *, approve: bool, body: str) -> None:
    flag = "--approve" if approve else "--comment"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8") as output:
        output.write(body)
        output.flush()
        gh("pr", "review", str(n), "--repo", repo, flag, "--body-file", output.name)


def post_issue_comment(repo: str, n: int, body: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8") as output:
        output.write(body)
        output.flush()
        gh("issue", "comment", str(n), "--repo", repo, "--body-file", output.name)
