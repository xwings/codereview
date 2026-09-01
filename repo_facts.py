"""Measured facts about a pull request, gathered before any model sees it.

Three of the seven checks start from something countable, and counting beats
asking: indentation is measured, added symbols are extracted, dependency lines
are diffed. The panel is told these are leads rather than verdicts — the
extractors are regex-based and will miss things, and a specialist that treats
this block as authoritative will be wrong about the cases that matter.
"""

from __future__ import annotations

import re
from pathlib import Path

import git_io

# The languages this tool supports as a first-class citizen: Python, C, C++
# and Rust. Each is measured for indentation here, has a symbol extractor
# below, and has a section in `prompts/coding_styles.md`. The config formats
# are carried too because every project has them. Anything else changed by the
# PR is listed but not judged — a convention this tool cannot measure is one
# the panel must establish from the tree instead.
INDENT_LANGS = {
    ".py": "spaces", ".c": "tabs", ".h": "tabs", ".cpp": "tabs", ".hpp": "tabs",
    ".rs": "spaces",
    ".sh": "spaces", ".yml": "spaces", ".yaml": "spaces", ".toml": "spaces",
}
MANIFESTS = ("pyproject.toml", "setup.py", "setup.cfg", "Cargo.toml")
MAX_SYMBOLS = 40

PY_SYMBOL_RE = re.compile(r"^\s*(?:async\s+)?(def|class)\s+([A-Za-z_]\w*)")
# A C definition: a line that opens a brace-bearing signature at column zero.
C_SYMBOL_RE = re.compile(r"^[A-Za-z_][\w\s*]*?\b([A-Za-z_]\w*)\s*\([^;]*$")
# A Rust item, in rustfmt's qualifier order: pub(…) default const async unsafe
# extern "abi", then the keyword. `impl` is deliberately absent — it introduces
# no new name. Trait method signatures match, which is wanted: check 3 is
# looking for names the PR adds, defined here or not.
RUST_SYMBOL_RE = re.compile(
    r"^\s*(?:pub(?:\s*\([^)]*\))?\s+)?(?:default\s+)?(?:const\s+)?"
    r"(?:async\s+)?(?:unsafe\s+)?(?:extern\s+\"[^\"]*\"\s+)?"
    r"(?:fn|struct|enum|trait|union|type)\s+([A-Za-z_]\w*)"
)
REQUIREMENT_RE = re.compile(r"^[+-]\s*[\"']?([A-Za-z0-9][\w.\-]*)\s*[><=~!\"'\[,]")


def _added_lines(diff: str) -> dict[str, list[str]]:
    """Map each touched path to the lines the diff adds to it."""
    per_file: dict[str, list[str]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current = path[2:] if path.startswith("b/") else path
            if current == "/dev/null":
                current = None
            elif current:
                per_file.setdefault(current, [])
        elif current and line.startswith("+") and not line.startswith("+++"):
            per_file[current].append(line[1:])
    return per_file


def _manifest_changes(diff: str) -> list[str]:
    """Requirement-looking lines added or removed in a dependency manifest."""
    out: list[str] = []
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current = path[2:] if path.startswith("b/") else path
        if not current:
            continue
        name = Path(current).name
        if name not in MANIFESTS and not name.startswith("requirements"):
            continue
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")) and REQUIREMENT_RE.match(line):
            out.append(f"{current}: {line}")
    return out


def _indent_of(lines: list[str]) -> str:
    """Classify the indentation a body of lines uses."""
    tabs = sum(1 for ln in lines if ln.startswith("\t"))
    spaces = sum(1 for ln in lines if ln.startswith("  "))
    if tabs and spaces:
        return f"MIXED ({tabs} tab-indented, {spaces} space-indented)"
    if tabs:
        return f"tabs ({tabs} lines)"
    if spaces:
        return f"spaces ({spaces} lines)"
    return "no indented lines"


def _repo_indent_baseline(clone: Path, ext: str) -> str:
    """How the rest of the repo indents files of this extension."""
    def count(pattern: str) -> int:
        res = git_io.git("grep", "-l", "-e", pattern, "--", f"*{ext}", cwd=clone, check=False)
        return len(res.stdout.split()) if res.returncode == 0 else 0

    tabs, spaces = count("^\t"), count("^    ")
    if not tabs and not spaces:
        return "no baseline found"
    return f"{tabs} tracked *{ext} files indent with tabs, {spaces} with 4 spaces"


def _symbols(path: str, lines: list[str]) -> list[str]:
    suffix = Path(path).suffix
    found = []
    if suffix == ".py":
        for ln in lines:
            m = PY_SYMBOL_RE.match(ln)
            if m:
                found.append(m.group(2))
    elif suffix in (".c", ".h", ".cpp", ".hpp"):
        for ln in lines:
            m = C_SYMBOL_RE.match(ln)
            if m and m.group(1) not in ("if", "for", "while", "switch", "return", "sizeof"):
                found.append(m.group(1))
    elif suffix == ".rs":
        for ln in lines:
            m = RUST_SYMBOL_RE.match(ln)
            if m:
                found.append(m.group(1))
    return found


def _existing_hits(clone: Path, symbol: str) -> int:
    res = git_io.git("grep", "-c", "-w", "-e", symbol, cwd=clone, check=False)
    if res.returncode != 0:
        return 0
    return sum(int(ln.rsplit(":", 1)[1]) for ln in res.stdout.splitlines() if ":" in ln)


def collect(clone: Path, diff: str) -> str:
    """Render the measured-facts block that goes into the session topic."""
    per_file = _added_lines(diff)
    out: list[str] = [
        "These facts were measured from the diff and the checkout by the tool, "
        "not by a model. They are leads, not verdicts: the extractors are "
        "regex-based and miss cases. Confirm anything you intend to report."
    ]

    out.append("\n## Indentation of added lines (check 1)")
    judged = False
    for path, lines in sorted(per_file.items()):
        ext = Path(path).suffix
        if ext not in INDENT_LANGS or not lines:
            continue
        judged = True
        out.append(
            f"- `{path}` — added lines use {_indent_of(lines)}; "
            f"convention for {ext} is {INDENT_LANGS[ext]}; "
            f"repo baseline: {_repo_indent_baseline(clone, ext)}"
        )
    if not judged:
        out.append("- (no changed file in a language with a measured convention)")

    out.append("\n## Symbols this PR adds, and where those names already occur (check 3)")
    symbols: list[tuple[str, str]] = [
        (name, path) for path, lines in sorted(per_file.items()) for name in _symbols(path, lines)
    ]
    if not symbols:
        out.append("- (no new function or class definitions detected)")
    for name, path in symbols[:MAX_SYMBOLS]:
        hits = _existing_hits(clone, name)
        note = f"{hits} occurrence(s) of this name repo-wide (includes the PR's own)"
        out.append(f"- `{name}` added in `{path}` — {note}")
    if len(symbols) > MAX_SYMBOLS:
        out.append(f"- [... {len(symbols) - MAX_SYMBOLS} more symbols not listed ...]")

    out.append("\n## Dependency manifest changes (check 6)")
    manifest = _manifest_changes(diff)
    if manifest:
        out.extend(f"- `{line}`" for line in manifest)
    else:
        out.append(
            "- (no dependency manifest lines added or removed; a new import may "
            "still exist without a manifest change — check the imports too)"
        )

    out.append("\n## Files touched")
    out.append(", ".join(f"`{p}`" for p in sorted(per_file)) or "(none)")
    return "\n".join(out)
