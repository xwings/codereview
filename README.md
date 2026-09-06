# codereview

A branch-based review CLI for GitHub pull requests and issues. It uses
a panel of specialist agents to inspect architecture and source, challenge
findings, and produce a clear report. Every PR specialist and the chair votes
on whether the change is ready to merge.

## Setup

Requires Python 3.10+, a Rust toolchain and C linker to build kerness, Git 2.32+,
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
./code.sh --id 42 --repo owner/project --branch main --dry-run
```

`--id` accepts a positive GitHub PR or issue number and detects its kind.
`code.sh` forwards all arguments directly to `review.py` through the project
virtual environment. Argument parsing, stdout, stderr and exit status belong
to `review.py`; the launcher does not capture or reformat its output.

Options can also be passed directly:

```sh
./code.sh --id 42 --repo owner/project --branch main --dry-run \
  --api-key sk-example --api-base https://server --llm-model gpt-6-astra
```

The positional forms `auto 42`, `pr 42` and `issue 42` remain supported; use
either a positional form or `--id`. `--repo` accepts `owner/name` and github.com
repository URLs. Both `--repo` and `--branch` are required. `--branch` selects
the remote branch used for analysis and replaces `--base-branch` and profile
branch pins; there is no default project or branch.

## Workflow

1. Identify whether the number names a PR or an issue. A mismatched explicit
   kind stops before source preparation.
2. Fetch the selected `--branch` into an isolated local source repository.
   Issues use that exact branch snapshot. For a PR, fetch its pinned head and
   merge it locally into the selected branch snapshot. A conflict or changed
   fetched head stops before documentation, model calls or posting.
3. Fetch the latest [eatmycode](https://github.com/xwings/eatmycode) specification
   and check only the final source's root `ARCHITECTURE.md` version, once. A
   matching version skips documentation preparation. A missing root or an
   absent, invalid or older version runs the documentation panel in a separate
   local guide worktree.
4. Read the source architecture, prepared guide when needed, related module
   docs and full source. For a PR: study → review → debate → verify → vote.
   For an issue: study → investigate → verify → answer.
5. Validate and print one report identifying the selected branch and reviewed
   revisions. Unless `--dry-run` is set, post it as a PR review or issue comment.

PR seats cover language conventions, API design, refactoring, code quality,
architecture, supply-chain risk and security. Each specialist casts its own
ballot; the chair cannot invent missing votes. Approval requires unanimous
support, complete passing checks, justified need and no unresolved major or
blocker findings. A hold is reported as a hold, rather than a rejection.

The PR merge exists only in the isolated local source repository. The tool
never merges a PR on GitHub, pushes, closes PRs/issues or applies labels. It
never runs the target project's tests, builds or scripts. Source preparation
isolates Git configuration and disables hooks, custom merge drivers and filters.
Managed clones with initialized submodules are refused; use a workdir without
initialized submodules.
Documentation preparation inspects source and validates structure; it does not
certify that target tests pass. Missing evidence remains explicit.

PR diffs compare the pinned selected branch with the local merge result.
Findings cite that merged source, whose lines may differ from the PR head on
GitHub. Generated guide edits are excluded from citations.

## Common options

| Option | Effect |
| --- | --- |
| `--id number` | Identify a PR or issue automatically. |
| `--branch name` | Required remote branch for issue analysis and the local PR merge. |
| `--dry-run` | Print the report without posting; documentation uses the same root-version gate. |
| `--allow-approve` | Permit a real GitHub approval after all approval gates pass. Otherwise post a comment. |
| `--verbose` | Add the full panel discussion to the default progress output on stderr. |
| `--transcript path.txt` | Save the discussion; a documentation panel uses a sibling `*-pr-N-docs` or `*-issue-N-docs` file. |
| `--workdir path` | Store managed clones, isolated sources and guide worktrees here; defaults to this tool's `repo/`. |
| `--prompts path` | Supply a custom supplementary repository profile. |
| `--timeout seconds` | Per-model-request timeout; defaults to 180. |
| `--max-turns n` | Override each panel's turn budget. An incomplete panel cannot publish. |

The API key and model also accept `--api-key` and `--llm-model`. Credentials
are not written into session files. See `./code.sh --help` for all options.

Progress shows each preparation step, the specialist waiting for a model
response or inspecting evidence, and completed turns within each panel phase.
While work is running, a heartbeat reports the current activity and elapsed
time every 15 seconds, including during slow Git, GitHub and model requests.
Successful steps show their total duration. This is enabled by default;
`--verbose` adds the full discussion.

Progress is flushed to stderr; stdout contains the final Markdown report:

```sh
./code.sh --id 42 --repo owner/project --branch main --dry-run > review.md
```

Independent source repositories and their documentation worktrees are retained
under `<workdir>/.reviews/`; their paths appear in progress output. A PR source
contains a synthetic local merge commit. The managed working tree and selected
branch are unchanged. Generated documentation stays uncommitted and is never pushed.
Inspect its diff before copying it into the target project. After preserving
any desired docs, remove guide worktrees with `git worktree remove` from their
source repository; independent source directories can then be removed.

The latest eatmycode check needs network access on every invocation. A fetch
failure or an unsupported upstream contract change stops the run instead of
silently accepting old rules. The integration supports eatmycode 1.1.0, including
versioned architecture and its root/module templates. An older or unversioned
root triggers content audit and migration; a newer root stops preflight until
the integration is updated. Original agent guidance and replaced or
removed documents are preserved in `ARCHITECTURE-ARCHIVE.md` in the local
documentation worktree when preparation runs, outside the coding documentation set.
Model calls can be substantial: a PR includes
at most one documentation panel plus the five-phase review panel. A current root
version skips preparation immediately: no module checks, structure/link/source
validation, guidance migration, documentation worktree or model calls. Existing
docs are read from the source snapshot. This version check does not certify
document contents; the PR/issue panel still inspects full relevant source.

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
