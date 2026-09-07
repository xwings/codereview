"""Git transport and isolated source snapshots for the repository under review."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from github_io import FORBIDDEN_GIT_PREFIXES, _check_prefix


@dataclass(frozen=True)
class Source:
    path: Path
    base_revision: str
    revision: str
    diff: str


def git(*args: str, cwd: Path | None = None, check: bool = True,
        isolated: bool = False, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    _check_prefix(args, FORBIDDEN_GIT_PREFIXES, "git")
    environment = os.environ.copy()
    if isolated:
        environment = {key: value for key, value in environment.items() if not key.startswith("GIT_")}
        environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=os.devnull,
                           GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM="1")
    if env:
        environment.update(env)
    res = subprocess.run(
        ["git", "-c", f"core.hooksPath={os.devnull}", "-c", "core.fsmonitor=false",
         "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "submodule.recurse=false", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=environment,
    )
    if check and res.returncode != 0:
        where = f" (cwd={cwd})" if cwd else ""
        raise SystemExit(
            f"error: `git {' '.join(args)}` failed (exit {res.returncode}){where}\n"
            f"  stderr: {res.stderr.strip() or '(empty)'}\n"
            f"  stdout: {res.stdout.strip() or '(empty)'}"
        )
    return res


def _filter_options(clone: Path) -> list[str]:
    result = git("config", "--null", "--name-only", "--get-regexp",
                 r"^filter\..*\.(clean|smudge|process|required)$", cwd=clone, check=False)
    if result.returncode not in (0, 1):
        raise SystemExit("error: could not inspect Git filter configuration safely.")
    names = {key.rsplit(".", 1)[0] for key in result.stdout.split("\0") if key}
    return [option for name in sorted(names) for setting in ("clean=", "smudge=", "process=", "required=false")
            for option in ("-c", f"{name}.{setting}")]


def ensure_clone(workdir: Path, repo: str) -> Path:
    """Ensure a clone of `repo` exists at workdir/<repo-name>. Returns its path."""
    workdir.mkdir(parents=True, exist_ok=True)
    name = repo.split("/")[-1]
    clone = workdir / name
    remote = f"https://github.com/{repo}.git"
    if not clone.exists():
        git("-c", "init.templateDir=", "clone", "--no-checkout", remote, str(clone))
        git(*_filter_options(clone), "reset", "--hard", "HEAD", cwd=clone)
        return clone
    # Same directory name can hold a clone of a different repo (e.g. a fork
    # via --repo). Refuse rather than reuse another repository's source.
    origin = git("remote", "get-url", "origin", cwd=clone).stdout.strip()
    if origin.rstrip("/").removesuffix(".git") != remote.removesuffix(".git"):
        raise SystemExit(
            f"error: {clone} is a clone of {origin}, expected {remote}.\n"
            f"  remove it or pass a different --workdir."
        )
    return clone


def assert_clone_clean(clone: Path) -> None:
    entries = git("ls-files", "--stage", "-z", cwd=clone).stdout.split("\0")
    for entry in entries:
        if entry.startswith("160000 "):
            path = clone / entry.split("\t", 1)[1]
            if (path / ".git").exists() or (path / ".git").is_symlink():
                raise SystemExit(
                    f"error: initialized submodule {path} cannot be checked without reading nested Git configuration.\n"
                    "  preserve it and choose a workdir without initialized submodules."
                )
    res = git(*_filter_options(clone), "status", "--porcelain", cwd=clone)
    if res.stdout.strip():
        raise SystemExit(
            f"error: {clone} has uncommitted changes.\n"
            "  preserve or commit them, or choose a different --workdir."
        )


def validate_branch(branch: str) -> str:
    if not branch or branch == "HEAD" or branch.startswith("-") or git(
        "check-ref-format", f"refs/heads/{branch}", check=False,
    ).returncode != 0:
        raise ValueError("--branch must name a valid branch, such as main or release/1.0")
    return branch


def prepare_source(clone: Path, workdir: Path, branch: str, *,
                   pr_number: int | None = None, pr_head: str | None = None) -> Source:
    """Pin the selected branch, then merge an optional PR in an isolated repository."""
    validate_branch(branch)
    installed = re.match(r"git version (\d+)\.(\d+)", git("--version").stdout)
    if installed is None or tuple(map(int, installed.groups())) < (2, 32):
        raise SystemExit("error: Git 2.32 or newer is required for isolated source preparation.")
    assert_clone_clean(clone)
    namespace = f"refs/codereview/{uuid.uuid4().hex}"
    base_ref, head_ref = f"{namespace}/base", f"{namespace}/head"
    try:
        git("fetch", "--no-tags", "--no-recurse-submodules", "--no-write-fetch-head", "--refmap=",
            "origin", f"refs/heads/{branch}:{base_ref}", cwd=clone)
        base = git("rev-parse", "--verify", f"{base_ref}^{{commit}}", cwd=clone).stdout.strip()
        head = None
        if pr_number is not None:
            git("fetch", "--no-tags", "--no-recurse-submodules", "--no-write-fetch-head", "--refmap=",
                "origin", f"refs/pull/{pr_number}/head:{head_ref}", cwd=clone)
            head = git("rev-parse", "--verify", f"{head_ref}^{{commit}}", cwd=clone).stdout.strip()
            if head != pr_head:
                raise SystemExit("error: PR head changed during fetch. Nothing posted; re-run the review.")

        parent = workdir.resolve() / ".reviews"
        parent.mkdir(parents=True, exist_ok=True)
        label = f"pr-{pr_number}-source" if pr_number is not None else "branch-source"
        source = Path(tempfile.mkdtemp(prefix=f"{clone.name}-{label}-", dir=parent))
        source.rmdir()
        git("-c", "init.templateDir=", "clone", "--local", "--no-checkout", "--no-hardlinks",
            "--dissociate", "--", str(clone.resolve()), str(source), isolated=True)
    finally:
        for ref in (base_ref, head_ref):
            git("update-ref", "-d", ref, cwd=clone)
    git("checkout", "--detach", base, cwd=source, isolated=True)
    revision = base
    diff = ""
    if head is not None:
        identity = ("-c", "user.name=Code review", "-c", "user.email=review@example.invalid")
        merged = git(*identity, "merge", "--no-commit", "--no-ff", "--no-edit", "--no-stat",
                     head, cwd=source, isolated=True, check=False)
        if merged.returncode != 0:
            raise SystemExit(
                f"error: PR #{pr_number} could not be merged into {branch}. Nothing posted.\n"
                f"  inspect the retained source workspace: {source}"
            )
        tree = git("write-tree", cwd=source, isolated=True).stdout.strip()
        dates = git("show", "--no-patch", "--format=%ct", base, head, cwd=source, isolated=True).stdout.splitlines()
        timestamp = f"{max(map(int, dates))} +0000"
        revision = git(
            *identity, "commit-tree", tree, "-p", base, "-p", head,
            "-m", f"Review PR #{pr_number} merged into {branch}", cwd=source, isolated=True,
            env={"GIT_AUTHOR_DATE": timestamp, "GIT_COMMITTER_DATE": timestamp},
        ).stdout.strip()
        git("reset", "--hard", revision, cwd=source, isolated=True)
        diff = git("diff", "--no-ext-diff", "--no-textconv", base, revision,
                   cwd=source, isolated=True).stdout
    return Source(source, base, revision, diff)


def review_workspace(clone: Path, workdir: Path, label: str) -> Path:
    """Keep documentation edits in a retained, detached review worktree."""
    parent = workdir.resolve() / ".reviews"
    parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=f"{clone.name}-{label}-", dir=parent))
    workspace.rmdir()
    git("worktree", "add", "--detach", str(workspace), "HEAD", cwd=clone, isolated=True)
    return workspace
