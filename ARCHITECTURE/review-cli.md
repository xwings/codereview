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

- `review.py:100` - `parse_args()` - CLI surface: `kind number`, plus `--api-key`, `--api-base`, `--llm-model` (env fallbacks `REVIEW_API_KEY`, `REVIEW_API_BASE`, `REVIEW_MODEL`), `--repo`, `--prompts`, `--base-branch`, `--dry-run`, `--allow-approve`, `--workdir`, `--timeout`, `--max-turns`, `--transcript`.
  **Breaking changes:** the old `<backend>` positional is gone, and `--repo` — which once carried a default repository — is now required. `./review.py claude pr 123` is now `./review.py pr 123 --repo o/n --llm-model …`. Requiring it is the point: a code-review tool with a default project reviews that project's conventions by accident whenever the flag is forgotten.
- `review.py:67` - `normalize_repo(value)` - **the CLI's input boundary.** Accepts `OWNER/NAME` and the github.com URL forms people paste (`github.com/o/n`, `https://github.com/o/n[.git]`, `git@github.com:o/n.git`, `ssh://`, `user@`), returns canonical `owner/name`. Validation is load-bearing, not politeness: this value becomes both a filesystem path (the profile lookup, the clone directory) and a subprocess argv, so each half must match `[A-Za-z0-9._-]+` and must not be `.`/`..` — `--repo ../../etc` is a clean exit, not a traversal. Non-github.com hosts are refused because every GitHub call goes through `gh` against github.com (guardrail 1), so another host would silently review the wrong thing.
- `review.py:161` - `resolve_profile(repo, override)` / `review.py:208` - `_read_prompt(profile, name, required)` - which knowledge the panel gets, and the profile → `default/` → `prompts/` search path. See [prompts.md](prompts.md).
- `review.py:196` - `resolve_base_branch(repo, profile, override, pr_base)` - `--base-branch` → the PR's own base → the profile's pin → the repo's GitHub default, the last one looked up lazily. See [git-io.md](git-io.md).
- `review.py:226` - `_truncate(text, budget)` - 60 KB byte budget (`DIFF_BUDGET_BYTES`, review.py:23). Lower than the old 200 KB on purpose: the full checkout is reachable through `read_file`, and the topic is replayed into every one of ~60 model calls.
- `review.py:262` - `build_pr_topic(...)` - concatenates the architecture reference, the rubric, the style reference, the measured facts, and the case itself — the first three from the resolved profile. Plain f-string — nothing user-controlled is substituted a second time.
- `review.py:331` - `require_body(fields, result, key)` - **the guard that matters.** kerness's result parsing never errors; a model that botches the closing JSON block yields type-appropriate *defaults*, i.e. an empty `review_body`. So: empty body → fall back to `result.summary`; that also empty → exit non-zero **without posting**. An empty review must never reach GitHub.
- `review.py:376` - `downgrade_if_needed(fields)` - `approve` plus any major/blocker finding → `comment`, with the override noted in the body. It reads the severity vocabulary every `design.md` is required to define, via `BLOCKING` (review.py:38) — the same tuple `render_summary` splits on, so the verdict line and the issue sections can never disagree about what blocks a merge.
- `review.py:496` - `render_summary(verdict, findings, clone)` - **the head of every posted review**, rendered here rather than left to the panel's prose. One line for the decision — `**Verdict: APPROVE**` or `**Verdict: REJECT**` — then one `## Issue N` section per blocker/major finding, then nit/info as a plain list under *Suggestions*. One issue never shares a section with another: a section naming two problems gets fixed halfway. Suggestions stay a list because a nit given the weight of a section reads like a blocker. The verdict shown is the panel's own, not the posting mode: with `approve` gated by `--allow-approve` the summary still says APPROVE, and the note beneath it says why a comment was posted instead.
- `review.py:481` - `render_issue(number, finding, clone)` - one issue, one section: the location, the cited lines, `**Problem.**`, `**How to change it.**` from the finding's `fix`, and the fix as code from `propose_code`. Both halves are code because the question is: an issue quoted as six lines of C and answered in one sentence leaves the contributor to guess the shape of the fix.
- `review.py:404` - `quote_code(clone, finding)` - **why a finding is about the PR's code and not about a recollection of it.** The cited lines are read from the checkout (±`EXCERPT_CONTEXT_LINES`, review.py:42, `>` on the cited line), never taken from the panel, so what the contributor reads is what they wrote. A path or line that is not in the checkout cannot be quoted and publishes as *unverified* in place of the code, which is the visible failure the maintainer needs — the alternative is a section that looks like evidence and quotes nothing. The finding's `file` comes out of a model, so it is resolved under the clone and anything outside is refused, the same confinement the panel's own reads get from the `AccessPolicy` (see [harness.md](harness.md)).
- `review.py:458` - `propose_code(finding)` - the fix as code, from the finding's `fix_code`, fenced in the file's language (`FENCE_LANGS`, review.py:50, scoped to the same set `repo_facts.INDENT_LANGS` measures — anything else gets a plain fence rather than a guessed one). Unlike the excerpt this *is* model-written, so it is labelled a sketch to adapt rather than a patch to apply, and clipped at `FIX_CODE_MAX_LINES` (review.py:46). Absent, it says so — the panel skipping the code half of an answer is worth seeing.
- `review.py:446` - `_fence(body, lang)` - opens with a fence longer than the longest backtick run inside the body. `fix_code` is model-written and may itself contain a fenced block; at three backticks that block would close the fence early and spill the remainder of the review out as prose.
- `review.py:535` - `render_checklist(checklist)` - renders the seven checks as a table, so the posted review shows which ones passed and which raised a concern. A check the panel failed to report shows as `❔ ?`, which is visible rather than silently absent.
- `review.py:563` - `handle_pr(...)` - fetch → clone/clean/reset to the resolved base/`checkout_pr` (via [git-io.md](git-io.md)) → `repo_facts.collect` → topic → panel → verdict policy → post. The body is assembled summary and issue sections → override note → the panel's covering note → checklist → footer. `approve` is posted for real only with `--allow-approve`.
- `review.py:628` - `handle_issue(...)` - fetch issue + comments → clone/clean/reset → panel → always a comment. Suggested labels are printed to stderr, never applied (guardrail: no label management).
- `review.py:665` - `main()` - resolves the profile once, prints which one is in force (`repo` or `generic`) to stderr, then dispatches. The rubric decides what the review *means*, so it is announced rather than assumed.
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
.venv/bin/python - <<'EOF'   # pass = "ok empty guard", "ok downgrade" and "ok summary"
import tempfile
from pathlib import Path
from types import SimpleNamespace
from review import require_body, downgrade_if_needed, render_summary
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
clone = Path(tempfile.mkdtemp())                      # stands in for the PR checkout
(clone / "b.c").write_text("".join(f"stmt {i};\n" for i in range(1, 13)))
s = render_summary("comment", [
    {"severity": "nit", "file": "b.c", "line": 3, "message": "name"},
    {"severity": "blocker", "file": "b.c", "line": 9, "message": "overflow\nhere",
     "fix": "bound n by sizeof dst", "fix_code": "if (n > sizeof dst)\n\treturn -EINVAL;"},
    {"severity": "major", "file": "../outside.c", "line": 1, "message": "not in the checkout"},
], clone)
assert s.splitlines()[0] == "## Summary"
assert "**Verdict: REJECT**" in s        # one line, one word, no prose around it
one, two = s.index("## Issue 1 — blocker in `b.c:9`"), s.index("## Issue 2 — major")
assert one < two                         # a section each, severest first, never merged
assert ">  9 | stmt 9;" in s             # quoted from the checkout, cited line marked...
assert "   6 | stmt 6;" in s and "stmt 5;" not in s             # ...with its context, clipped
assert "**Problem.** overflow here" in s and "**How to change it.** bound n by sizeof dst" in s
assert "```c\nif (n > sizeof dst)\n\treturn -EINVAL;\n```" in s  # the fix as code, in the
assert "sketch to adapt, not a patch to apply" in s             # file's language, labelled
assert "no sample or pseudo-code" in s[two:]  # the issue with no fix_code says so, visibly
assert "`../outside.c` is not in the checkout" in s   # unquotable is visible, not silent
assert s.index("## Suggestions") > two   # the nit is a line below, not a section of its own
assert "- **nit** `b.c:3` — name" in s
assert render_summary("approve", [], clone).strip().endswith("**Verdict: APPROVE**")
# A fix_code that quotes a fenced block must not end the fence it is inside.
esc = render_summary("comment", [{"severity": "major", "file": "b.c", "line": 1, "message": "m",
                                  "fix_code": "```\nnested\n```"}], clone)
assert "````c\n```\nnested\n```\n````" in esc
# ...and one that runs long is clipped rather than posted whole.
long = render_summary("comment", [{"severity": "major", "file": "b.c", "line": 1, "message": "m",
                                   "fix_code": "\n".join(f"l{i}" for i in range(40))}], clone)
assert "l19" in long and "l20" not in long and "clipped at 20 lines" in long
print("ok summary")
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
