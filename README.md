# codereview

A documentation-first review CLI for GitHub pull requests and issues. It uses
a panel of specialist agents to inspect architecture and source, challenge
findings, and produce a clear report. Every PR specialist and the chair votes
on whether the change is ready to merge.

## Setup

Requires Python 3.10+, a Rust toolchain and C linker to build kerness, `git`,
and an authenticated [GitHub CLI](https://cli.github.com/). Linux and macOS
are supported.

```sh
git clone https://github.com/xwings/codereview.git
cd codereview
python3 -m venv .venv
git clone https://github.com/xwings/kerness.git vendor/kerness
git -C vendor/kerness checkout --detach 7c97dcb4e50a8fd05d05185b0052ba1356be016a
git -C vendor/kerness apply ../../patches/kerness-pyo3.patch
MATURIN_PEP517_ARGS='--locked' .venv/bin/pip install ./vendor/kerness/bindings/python
.venv/bin/python -m kerness.selfcheck
gh auth login
```

These one-time installation commands build a pinned kerness revision with the
tracked PyO3 update. `requirements.txt` records the installed version; kerness
is not on PyPI. An existing configured environment needs no installation step
when launching a review. See [patch provenance](patches/README.md).

Configure an OpenAI-compatible endpoint through environment variables:

```sh
export REVIEW_API_KEY='your-key'
export REVIEW_MODEL='your-model'
export REVIEW_API_BASE='https://api.openai.com/v1'  # optional default
./code.sh --id 42 --repo owner/project --dry-run
```

`--id` accepts a positive GitHub PR or issue number and detects its kind.
`code.sh` forwards all arguments directly to `review.py` through the project
virtual environment. Argument parsing, stdout, stderr and exit status belong
to `review.py`; the launcher does not capture or reformat its output.

Options can also be passed directly:

```sh
./code.sh --id 42 --repo owner/project --dry-run \
  --api-key sk-example --api-base https://server --llm-model gpt-6-astra
```

The positional forms `auto 42`, `pr 42` and `issue 42` remain supported; use
either a positional form or `--id`. `--repo` accepts `owner/name` and github.com
repository URLs. There is no default project.

## Workflow

1. Fetch the latest [eatmycode](https://github.com/xwings/eatmycode)
   specification. Inspect the repository and create or update its architecture
   documents in a local review worktree. Preserve existing agent guidance.
2. Identify whether the number names a PR or an issue. For a PR, audit its own
   head's documentation too; default-branch documentation can be out of date
   for the proposed change.
3. Read the original `ARCHITECTURE.md` when present, the audited guide, related
   module docs and full source. Generated guides remain separate from the
   original source used for findings and citations.
4. For a PR: study → review → debate → verify → vote. For an issue: study →
   investigate → verify → answer.
5. Validate the result and print one report. Unless `--dry-run` is set, post
   it as a PR review or issue comment.

PR seats cover language conventions, API design, refactoring, code quality,
architecture, supply-chain risk and security. Each specialist casts its own
ballot; the chair cannot invent missing votes. Approval requires unanimous
support, complete passing checks, justified need and no unresolved major or
blocker findings. A hold is reported as a hold, rather than a rejection.

This tool never merges, pushes, closes issues or applies labels. It never
runs the target project's tests, builds or scripts. Documentation checks
verify structure and inspect source; they do not certify that target tests
pass. Missing evidence remains explicit.

## Common options

| Option | Effect |
| --- | --- |
| `--id number` | Identify a PR or issue automatically. |
| `--dry-run` | Print the report without posting; documentation is still prepared locally. |
| `--allow-approve` | Permit a real GitHub approval after all approval gates pass. Otherwise post a comment. |
| `--verbose` | Show the full panel discussion on stderr. Default output shows concise progress. |
| `--transcript path.txt` | Save the discussion; doc panels use sibling `*-baseline-docs` and `*-pr-N-docs` files. |
| `--workdir path` | Store managed clones and review worktrees here; defaults to this tool's `repo/`. |
| `--prompts path` | Supply a custom supplementary repository profile. |
| `--base-branch name` | Override the baseline branch used for checkout and initial documentation. The PR diff still uses its actual base. |
| `--timeout seconds` | Per-model-request timeout; defaults to 180. |
| `--max-turns n` | Override each panel's turn budget. An incomplete panel cannot publish. |

The API key and model also accept `--api-key` and `--llm-model`. Credentials
are not written into session files. See `./code.sh --help` for all options.

Progress goes to stderr; stdout contains the final Markdown report:

```sh
./code.sh --id 42 --repo owner/project --dry-run > review.md
```

Local source and documentation worktrees are retained under
`<workdir>/.reviews/`, and their paths appear in progress output. Inspect the
generated documentation diff before copying it into the target project.
Nothing is automatically committed or pushed. Old worktrees consume disk;
after preserving any desired docs, remove them using `git worktree remove`
from the managed clone.

The latest eatmycode check needs network access on every invocation. A fetch
failure or an unsupported upstream contract change stops the run instead of
silently accepting old rules. Model calls can be substantial: a PR includes
two documentation panels plus the five-phase review panel.

## Development

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m kerness.selfcheck
./code.sh --help
```

Tests run offline with scripted model replies, temporary Git repositories and
mock GitHub calls. They exercise the real kerness session engine without
posting anything. A live smoke review uses the command above with `--dry-run`.

[ARCHITECTURE.md](ARCHITECTURE.md) is the development guide and subsystem index.
The upstream eatmycode specification owns the shared development discipline;
repository profiles and persona files remain project-neutral.
