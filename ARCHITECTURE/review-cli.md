# review-cli (review.py, repo_facts.py)

## Goal

CLI entry point and orchestrator: parses arguments, gathers the case, measures
what can be measured, assembles the session topic, runs the kerness panel, maps
its typed result to a verdict, enforces the approval policy, and dispatches to
GitHub. Infrastructure — this is the program itself.

## Status

`done` — the How to Test commands pass.

## Code Structure

| File | Role |
| ---- | ---- |
| `review.py` | argparse CLI, topic assembly, result mapping, verdict policy, body rendering, PR/issue handlers |
| `repo_facts.py` | deterministic pre-pass feeding checks 1, 3 and 6 |

## Key Types and Entry Points

- `review.py:81` - `parse_args()` - CLI surface: `kind number`, plus `--api-key`, `--api-base`, `--llm-model` (env fallbacks `REVIEW_API_KEY`, `REVIEW_API_BASE`, `REVIEW_MODEL`), `--repo`, `--prompts`, `--base-branch`, `--dry-run`, `--allow-approve`, `--workdir`, `--timeout`, `--max-turns`, `--transcript`.
  **Breaking changes:** the old `<backend>` positional is gone, and `--repo` — which once carried a default repository — is now required. `./review.py claude pr 123` is now `./review.py pr 123 --repo o/n --llm-model …`. Requiring it is the point: a code-review tool with a default project reviews that project's conventions by accident whenever the flag is forgotten.
- `review.py:48` - `normalize_repo(value)` - **the CLI's input boundary.** Accepts `OWNER/NAME` and the github.com URL forms people paste (`github.com/o/n`, `https://github.com/o/n[.git]`, `git@github.com:o/n.git`, `ssh://`, `user@`), returns canonical `owner/name`. Validation is load-bearing, not politeness: this value becomes both a filesystem path (the profile lookup, the clone directory) and a subprocess argv, so each half must match `[A-Za-z0-9._-]+` and must not be `.`/`..` — `--repo ../../etc` is a clean exit, not a traversal. Non-github.com hosts are refused because every GitHub call goes through `gh` against github.com (guardrail 1), so another host would silently review the wrong thing.
- `review.py:142` - `resolve_profile(repo, override)` / `review.py:189` - `_read_prompt(profile, name, required)` - which knowledge the panel gets, and the profile → `default/` → `prompts/` search path. See [prompts.md](prompts.md).
- `review.py:177` - `resolve_base_branch(repo, profile, override, pr_base)` - `--base-branch` → the PR's own base → the profile's pin → the repo's GitHub default, the last one looked up lazily. See [git-io.md](git-io.md).
- `review.py:207` - `_truncate(text, budget)` - 60 KB byte budget (`DIFF_BUDGET_BYTES`, review.py:23). Lower than the old 200 KB on purpose: the full checkout is reachable through `read_file`, and the topic is replayed into every one of ~60 model calls.
- `review.py:243` - `build_pr_topic(...)` - concatenates the architecture reference, the rubric, the style reference, the measured facts, and the case itself — the first three from the resolved profile. Plain f-string — nothing user-controlled is substituted a second time.
- `review.py:312` - `require_body(fields, result, key)` - **the guard that matters.** kerness's result parsing never errors; a model that botches the closing JSON block yields type-appropriate *defaults*, i.e. an empty `review_body`. So: empty body → fall back to `result.summary`; that also empty → exit non-zero **without posting**. An empty review must never reach GitHub.
- `review.py:357` - `downgrade_if_needed(fields)` - `approve` plus any major/blocker finding → `comment`, with the override noted in the body. It reads the severity vocabulary every `design.md` is required to define.
- `review.py:390` - `render_checklist(checklist)` - renders the seven checks as a table, so the posted review shows which ones passed and which raised a concern. A check the panel failed to report shows as `❔ ?`, which is visible rather than silently absent.
- `review.py:418` - `handle_pr(...)` - fetch → clone/clean/reset to the resolved base/`checkout_pr` (via [git-io.md](git-io.md)) → `repo_facts.collect` → topic → panel → verdict policy → post. `approve` is posted for real only with `--allow-approve`.
- `review.py:479` - `handle_issue(...)` - fetch issue + comments → clone/clean/reset → panel → always a comment. Suggested labels are printed to stderr, never applied (guardrail: no label management).
- `review.py:516` - `main()` - resolves the profile once, prints which one is in force (`repo` or `generic`) to stderr, then dispatches. The rubric decides what the review *means*, so it is announced rather than assumed.
- `repo_facts.py:136` - `collect(clone, diff)` - measures indentation of added lines against the repo baseline (check 1), extracts added symbols with their repo-wide hit counts (check 3), and diffs dependency-manifest lines (check 6). The block opens by telling the panel these are leads, not verdicts — the extractors are regex-based and miss cases.
- `repo_facts.py:23` - `INDENT_LANGS` / `repo_facts.py:28` - `MANIFESTS` - the extensions and dependency manifests worth measuring. Scoped to the four core languages — Python, C, C++, Rust — plus shell and the usual config formats, so this table, `_symbols` and `prompts/coding_styles.md` cover the same set rather than three different ones. A language absent from it degrades to "no measured convention" rather than guessing, which is the correct outcome: check 1 would otherwise assert a convention nobody in this project has agreed to.
- `repo_facts.py:108` - `_symbols(path, lines)` - per-language definition extraction feeding check 3, one regex per family: `PY_SYMBOL_RE` (repo_facts.py:31) for `def`/`class`, `C_SYMBOL_RE` (repo_facts.py:33) for column-zero brace-bearing signatures with a keyword blacklist, `RUST_SYMBOL_RE` (repo_facts.py:38) for `fn`/`struct`/`enum`/`trait`/`union`/`type` behind rustfmt's qualifier order (`pub(…) default const async unsafe extern "abi"`). Rust's `impl` is deliberately not matched — it introduces no new name, so it is not a duplication lead.

## Interactions

- Calls [github-io.md](github-io.md) for every GitHub read/write.
- Calls [git-io.md](git-io.md) to prepare the checkout.
- Builds and runs the panel via [harness.md](harness.md).
- Loads the reference layers described in [prompts.md](prompts.md).

## How to Test

```sh
.venv/bin/python -m py_compile review.py repo_facts.py    # pass = exit 0
.venv/bin/python review.py --help                         # pass = exit 0, help lists --allow-approve, --prompts, --base-branch
.venv/bin/python review.py pr 1 --api-key k --llm-model m 2>&1 | grep -q 'required.*--repo' \
  && echo "ok --repo is required"                         # pass = exit 2, argparse names --repo
.venv/bin/python - <<'EOF'   # pass = every line "ok", no FAIL
import tempfile
from pathlib import Path
from review import normalize_repo, resolve_profile, DEFAULT_PROFILE_DIR
for v in ("owner/name", "github.com/a/b", "https://github.com/a/b.git",
          "git@github.com:a/b.git", "https://github.com/a/b/"):
    assert normalize_repo(v).count("/") == 1, v
print("ok url forms")
for bad in ("../../etc", "a/b/c", "https://gitlab.com/a/b", "a/..", "a", "a/b c"):
    try:
        normalize_repo(bad); print("FAIL accepted", bad)
    except SystemExit:
        pass
print("ok bad repos rejected")
# No profile ships, so every repo falls through to the generic one...
assert resolve_profile("any/repo", None) == DEFAULT_PROFILE_DIR
# ...and --prompts is the only way a run gets a curated directory.
tmp = Path(tempfile.mkdtemp())
assert resolve_profile("any/repo", tmp) == tmp
try:
    resolve_profile("any/repo", tmp / "nope"); print("FAIL non-directory accepted")
except SystemExit:
    pass
print("ok profile lookup")
EOF
.venv/bin/python - <<'EOF'   # pass = "ok generic topic"
from pathlib import Path
from review import build_pr_topic, resolve_profile
pr = {"number": 7, "url": "https://github.com/acme/widget/pull/7", "title": "t",
      "baseRefName": "main", "files": []}
t = build_pr_topic(pr, "diff", "facts", Path("/tmp"), resolve_profile("acme/widget", None))
assert "acme/widget" in t                       # the topic names the repo under review...
assert "No curated architecture reference" in t # ...and claims no knowledge of any other
print("ok generic topic")
EOF
# pass = "ok no project name is wired into the tool". The whole source tree, not
# just the Python: the name used to sit in prompts, personas and .gitignore too.
# The class in `qil[i]ng` keeps the pattern from matching the line you are
# reading; it still matches the name itself anywhere it comes back.
grep -rni --exclude-dir=.git --exclude-dir=.venv --exclude-dir=__pycache__ \
  --exclude-dir=repo --exclude-dir=vendor 'qil[i]ng' .
test $? -eq 1 && echo "ok no project name is wired into the tool"
.venv/bin/python - <<'EOF'   # pass = "ok empty guard" and "ok downgrade"
from types import SimpleNamespace
from review import require_body, downgrade_if_needed
r = SimpleNamespace(summary="", end_reason="max_turns", phase_reached="verify")
try:
    require_body({"review_body": "  "}, r, "review_body")
    print("FAIL empty body accepted")
except SystemExit:
    print("ok empty guard")
f, note = downgrade_if_needed({"verdict": "approve",
                               "findings": [{"severity": "blocker", "message": "x"}]})
assert f["verdict"] == "comment" and note
print("ok downgrade")
EOF
.venv/bin/python - <<'EOF'   # pass = "ok core languages", no FAIL
from repo_facts import _symbols, _manifest_changes, INDENT_LANGS, MANIFESTS
fail = 0
def want(path, line, expect):
    global fail
    got = _symbols(path, [line])
    if got != expect:
        print("FAIL", path, repr(line), "->", got); fail += 1
for line, name in [("pub fn foo(a: u8) {", "foo"), ("pub(crate) struct Qux {", "Qux"),
                   ('pub extern "C" fn ext() {', "ext"), ("pub const fn c() {", "c"),
                   ("pub unsafe trait T {", "T"), ("pub type Result<T> = ();", "Result"),
                   ("    fn trait_method(&self);", "trait_method")]:
    want("src/lib.rs", line, [name])
for line in ("impl Foo {", "impl Display for Foo {", "pub use foo::bar;",
             "const FOO: u32 = 1;", "static S: u8 = 0;", "mod m;", "// fn commented"):
    want("src/lib.rs", line, [])          # no name introduced -> no duplication lead
want("a.py", "def x():", ["x"]); want("a.c", "int foo(int a)", ["foo"])
want("a.go", "func x() {", [])            # not a core language: no leads, no guesses
assert INDENT_LANGS[".rs"] == "spaces" and ".go" not in INDENT_LANGS
assert "Cargo.toml" in MANIFESTS and "go.mod" not in MANIFESTS
assert len(_manifest_changes("+++ b/Cargo.toml\n+serde = \"1.0\"\n")) == 1
print("ok core languages" if not fail else f"{fail} FAILURES")
EOF
```

- Manual end-to-end (needs `gh auth`, an endpoint, and network):
  `.venv/bin/python review.py pr <N> --repo https://github.com/<owner>/<name> --api-key … --api-base … --llm-model … --dry-run`
  — pass = the URL is accepted, the `generic` profile is announced, the base
  branch comes from `gh`, four phases run, the printed body carries the
  seven-item checklist and cites only paths that exist in that repo, and nothing
  is posted.
- Same again with `--prompts <dir>` pointing at a hand-written profile — pass =
  the `repo` profile is announced instead, and the findings reflect that
  profile's rubric.

## Open Gaps / Roadmap

- Failure modes: missing `gh` → exit 2 with a hint; dirty clone → refusal;
  empty panel result → exit 1 with nothing posted; oversized diff → truncation
  marker plus a pointer to `read_file`.
- `--timeout` is now the per-request HTTP timeout, not a whole-run budget. A
  wall-clock ceiling for the full panel does not exist; `--max-turns` is the
  proxy.
- `repo_facts._symbols` (repo_facts.py:108) covers the four core languages and
  nothing else. A Go, JS/TS or Java PR gets no measured indentation (check 1),
  no manifest diff (check 6) and an empty check-3 lead list, so all three rest
  entirely on the seats' own reading and `repo_grep`. That is a deliberate
  scope, not an oversight — adding a language means a regex, an indent rule and
  a `coding_styles.md` section together, or the panel gets leads it cannot
  interpret.
- The Rust extractor is a regex, so it inherits the limits of one: a signature
  wrapped across lines is matched on the line carrying the keyword and name
  (correct) but a macro-generated item is invisible, and an item defined inside
  a function body is reported as if it were top-level. Both are misses toward
  fewer leads, never toward a false one, which is the safe direction for a block
  the panel is told to confirm before reporting.
- No profile ships, so every repo reviews against `prompts/default/` until
  someone writes one. That is a working review, not a degraded one, but a
  project the maintainer reviews often deserves its own — see
  [prompts.md](prompts.md).
- Inline line-level comments, batch mode, and caching remain out of scope.
