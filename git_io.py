"""Local git operations on the script-owned clone of the repo under review."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from github_io import FORBIDDEN_GIT_PREFIXES, _check_prefix, gh


def git(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    _check_prefix(args, FORBIDDEN_GIT_PREFIXES, "git")
    res = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if check and res.returncode != 0:
        where = f" (cwd={cwd})" if cwd else ""
        raise SystemExit(
            f"error: `git {' '.join(args)}` failed (exit {res.returncode}){where}\n"
            f"  stderr: {res.stderr.strip() or '(empty)'}\n"
            f"  stdout: {res.stdout.strip() or '(empty)'}"
        )
    return res


def ensure_clone(workdir: Path, repo: str) -> Path:
    """Ensure a clone of `repo` exists at workdir/<repo-name>. Returns its path."""
    workdir.mkdir(parents=True, exist_ok=True)
    name = repo.split("/")[-1]
    clone = workdir / name
    remote = f"https://github.com/{repo}.git"
    if not clone.exists():
        git("clone", remote, str(clone))
        return clone
    # Same directory name can hold a clone of a different repo (e.g. a fork
    # via --repo). Refuse rather than hard-reset against the wrong remote.
    origin = git("remote", "get-url", "origin", cwd=clone).stdout.strip()
    if origin.rstrip("/").removesuffix(".git") != remote.removesuffix(".git"):
        raise SystemExit(
            f"error: {clone} is a clone of {origin}, expected {remote}.\n"
            f"  remove it or pass a different --workdir."
        )
    return clone


def assert_clone_clean(clone: Path) -> None:
    res = git("status", "--porcelain", cwd=clone)
    if res.stdout.strip():
        raise SystemExit(
            f"error: {clone} has uncommitted changes.\n"
            f"  inspect, then `git -C {clone} reset --hard && git -C {clone} clean -fd` to start fresh."
        )


def reset_to_branch(clone: Path, branch: str) -> None:
    """Fetch and hard-reset the clone to `origin/<branch>`."""
    git("fetch", "origin", cwd=clone)
    git("checkout", branch, cwd=clone)
    git("reset", "--hard", f"origin/{branch}", cwd=clone)


def checkout_pr(clone: Path, repo: str, n: int, short_sha: str) -> str:
    """Checkout the PR into a fresh `review/pr-<n>-<sha>` branch. Returns branch name."""
    branch = f"review/pr-{n}-{short_sha}"
    # Drop any previous review branches for this PR (force-pushes change the
    # sha, so match the prefix). We're on the base branch already.
    existing = git("branch", "--list", f"review/pr-{n}-*", cwd=clone, check=False)
    for stale in existing.stdout.split():
        if stale != "*":
            git("branch", "-D", stale, cwd=clone)
    gh("pr", "checkout", str(n), "--repo", repo, "-b", branch, cwd=clone)
    return branch


def review_workspace(clone: Path, workdir: Path, label: str) -> Path:
    """Keep documentation edits in a retained, detached review worktree."""
    parent = workdir.resolve() / ".reviews"
    parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=f"{clone.name}-{label}-", dir=parent))
    workspace.rmdir()  # git creates the directory itself
    git("worktree", "add", "--detach", str(workspace), "HEAD", cwd=clone)
    return workspace


def require_head(clone: Path, expected: str) -> None:
    actual = git("rev-parse", "HEAD", cwd=clone).stdout.strip()
    if actual != expected:
        raise SystemExit("error: PR head changed during checkout. Nothing posted; re-run the review.")


def pr_diff(clone: Path, base: str) -> str:
    """Diff the checked-out revision, so the topic and source cannot race."""
    git("fetch", "origin", base, cwd=clone)
    merge_base = git("merge-base", "FETCH_HEAD", "HEAD", cwd=clone).stdout.strip()
    return git("diff", "--no-ext-diff", "--no-textconv", merge_base, "HEAD", cwd=clone).stdout
