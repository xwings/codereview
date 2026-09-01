"""Tools the review panel may call.

Three, and no more: search the checkout, look up a package's health, look up a
GitHub repository's health. The `cmd` tool is never registered — see
gameplans/pr_review.md, whose `tools:` list is what makes that structural.

Every handler returns a string. A failure is described in that string rather
than raised: a tool that raises costs the agent its turn, while a tool that
explains itself lets the agent route around the gap and say so in the review.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

import git_io
import github_io

# Caps. A tool result is replayed into every later turn, so an uncapped grep
# over a large repo would cost the whole session's context.
MAX_GREP_LINES = 80
MAX_LINE_CHARS = 300
NET_TIMEOUT_S = 15

PYPI_URL = "https://pypi.org/pypi/{name}/json"
OSV_URL = "https://api.osv.dev/v1/query"

Handler = Callable[[dict[str, Any]], str]
Tool = tuple[str, str, dict[str, Any], Handler]


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as resp:
        return json.load(resp)


def _post_json(url: str, payload: dict[str, Any]) -> Any:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT_S) as resp:
        return json.load(resp)


def _clip(lines: list[str]) -> str:
    shown = [ln[:MAX_LINE_CHARS] for ln in lines[:MAX_GREP_LINES]]
    if len(lines) > MAX_GREP_LINES:
        shown.append(f"[... {len(lines) - MAX_GREP_LINES} more matches, narrow the pattern ...]")
    return "\n".join(shown)


def make_repo_grep(clone: Path) -> Tool:
    """Search the checkout. Backed by `git grep`, so only tracked files match."""

    def handler(args: dict[str, Any]) -> str:
        pattern = str(args.get("pattern") or "").strip()
        if not pattern:
            return "error: `pattern` is required."
        argv = ["grep", "-n", "-I", "--no-color", "-e", pattern]
        glob = str(args.get("glob") or "").strip()
        if glob:
            argv += ["--", glob]
        res = git_io.git(*argv, cwd=clone, check=False)
        if res.returncode == 1:
            return f"no matches for {pattern!r}" + (f" in {glob}" if glob else "")
        if res.returncode != 0:
            return f"error: git grep failed: {res.stderr.strip() or '(no stderr)'}"
        return _clip(res.stdout.splitlines())

    schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Basic regular expression to search for.",
            },
            "glob": {
                "type": "string",
                "description": "Optional pathspec to limit the search, e.g. 'src/**/*.py'.",
            },
        },
        "required": ["pattern"],
    }
    description = (
        "Search the tracked files of the repository checkout for a pattern. "
        "Returns matching 'path:line:text' lines, capped. Use this to find how "
        "the project already names things, where similar code lives, and "
        "whether a symbol is used anywhere else."
    )
    return ("repo_grep", description, schema, handler)


def make_package_health() -> Tool:
    """Release history and known advisories for a PyPI package."""

    def handler(args: dict[str, Any]) -> str:
        name = str(args.get("name") or "").strip()
        if not name:
            return "error: `name` is required."

        out: list[str] = [f"# {name} (PyPI)"]
        try:
            data = _get_json(PYPI_URL.format(name=urllib.parse.quote(name, safe="")))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return (
                    f"{name}: no such project on PyPI. If the patch imports it, the "
                    f"name may be misspelled, vendored, or come from another index — "
                    f"which is itself worth reporting."
                )
            return f"{name}: PyPI lookup failed (HTTP {e.code}); report as unverified."
        except Exception as e:  # network down, DNS, timeout, malformed JSON
            return f"{name}: PyPI lookup failed ({type(e).__name__}); report as unverified."

        info = data.get("info") or {}
        releases = data.get("releases") or {}
        dates = sorted(
            f["upload_time_iso_8601"]
            for files in releases.values()
            for f in files
            if f.get("upload_time_iso_8601")
        )
        out.append(f"summary: {info.get('summary') or '(none)'}")
        out.append(f"latest version: {info.get('version') or '?'}")
        out.append(f"releases: {len(releases)}")
        if dates:
            out.append(f"first release: {dates[0]}")
            out.append(f"most recent release: {dates[-1]}")
        out.append(f"author: {info.get('author') or '(unset)'}")
        out.append(f"maintainer: {info.get('maintainer') or '(unset)'}")
        out.append(f"license: {info.get('license') or '(unset)'}")
        out.append(f"requires: {', '.join(info.get('requires_dist') or []) or '(none declared)'}")
        urls = info.get("project_urls") or {}
        out.append(f"project urls: {json.dumps(urls) if urls else '(none)'}")
        yanked = [v for v, files in releases.items() if any(f.get("yanked") for f in files)]
        if yanked:
            out.append(f"yanked releases: {', '.join(sorted(yanked)[:10])}")

        out.append("")
        out.append("## Advisories (OSV, includes GHSA)")
        try:
            osv = _post_json(OSV_URL, {"package": {"name": name, "ecosystem": "PyPI"}})
            vulns = osv.get("vulns") or []
            if not vulns:
                out.append("none known")
            for v in vulns[:10]:
                ids = ", ".join([v.get("id", "?"), *(v.get("aliases") or [])])
                out.append(f"- {ids}: {(v.get('summary') or '(no summary)')[:200]}")
            if len(vulns) > 10:
                out.append(f"- [... {len(vulns) - 10} more ...]")
        except Exception as e:
            out.append(f"lookup failed ({type(e).__name__}); report as unverified")

        return "\n".join(out)

    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "PyPI project name, e.g. 'capstone'."},
        },
        "required": ["name"],
    }
    description = (
        "Look up a PyPI package: release count and dates, maintainer and license "
        "metadata, declared requirements, yanked releases, and known security "
        "advisories from OSV (which includes GHSA). Use this to answer whether a "
        "proposed dependency is still maintained and whether it is vulnerable."
    )
    return ("package_health", description, schema, handler)


def make_github_repo_health() -> Tool:
    """Upstream activity for a GitHub repository, through the `gh` chokepoint."""

    def handler(args: dict[str, Any]) -> str:
        repo = str(args.get("repo") or "").strip()
        if repo.count("/") != 1 or not all(part for part in repo.split("/")):
            return "error: `repo` must be 'owner/name'."
        fields = (
            "name,description,isArchived,isFork,pushedAt,createdAt,updatedAt,"
            "stargazerCount,forkCount,licenseInfo,securityPolicyUrl,url"
        )
        res = github_io.gh("repo", "view", repo, "--json", fields, check=False)
        if res.returncode != 0:
            return (
                f"{repo}: gh lookup failed — {res.stderr.strip() or '(no stderr)'}. "
                f"Report as unverified."
            )
        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError:
            return f"{repo}: gh returned unparseable JSON; report as unverified."
        lic = (data.get("licenseInfo") or {}).get("spdxId") or "(none)"
        return "\n".join(
            [
                f"# {repo}",
                f"description: {data.get('description') or '(none)'}",
                f"archived: {data.get('isArchived')}",
                f"fork: {data.get('isFork')}",
                f"created: {data.get('createdAt')}",
                f"last push: {data.get('pushedAt')}",
                f"stars: {data.get('stargazerCount')}  forks: {data.get('forkCount')}",
                f"license: {lic}",
                f"security policy: {data.get('securityPolicyUrl') or '(none)'}",
                f"url: {data.get('url')}",
            ]
        )

    schema = {
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "Repository as 'owner/name'."},
        },
        "required": ["repo"],
    }
    description = (
        "Look up a GitHub repository's upstream health: archived flag, last push, "
        "age, stars, license, and whether it publishes a security policy. Use this "
        "on the upstream of a proposed dependency to judge whether it is alive."
    )
    return ("github_repo_health", description, schema, handler)


def pr_tools(clone: Path) -> list[Tool]:
    return [make_repo_grep(clone), make_package_health(), make_github_repo_health()]


def issue_tools(clone: Path) -> list[Tool]:
    return [make_repo_grep(clone)]
