# codereview

A branch-based review CLI for GitHub pull requests and issues. It uses
a lead reviewer to inspect architecture and source, with independent
verification for every PR and for issues that need it. The result is one
evidence-backed report with explicit findings and remaining questions.

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
`--verbose` is optional: the command above runs the complete review and prints
the final report with progress on stderr. Add `--verbose` to see the panel discussion.

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
   and read its `metadata.version`. Check the final source's `ARCHITECTURE.md`
   and every Markdown file recursively under `ARCHITECTURE/`. If all versions
   match and layout, sizes and navigation pass, proceed. The eatmycode 2.0
   layout separates a small root (6,000 characters), mandatory Agent Rules
   (12,000), modules (8,000), conditional topics (6,000) and indexes (4,000).
   Missing, stale, malformed or oversized docs run preparation in a separate
   local guide worktree. Legacy pages migrate with their useful guidance retained.
4. Reuse the root and Agent Rules supplied once in the review topic. Match PR
   paths or issue symptoms to Task Index routes, then read only affected owners,
   triggered topics and full relevant source. Follow partner docs only when a
   boundary is affected; broad changes proceed in owner batches.
   For a PR: lead review → optional focused consultation
   → independent verification. For an issue: investigate → verify if needed.
5. Validate and print one report identifying the selected branch and reviewed
   revisions. Unless `--dry-run` is set, post it as a PR review or issue comment.

PRs normally need two review turns: **Lead** reviews all seven checks, then
**Verifier** independently checks the evidence and conclusions. Style and naming
remain separate checks within the same review. Lead can request Security or
Dependencies once each for a concrete question before verification. The host
selects the reviewers directly; there are no chair-routing, debate, voting or
closing-draft rounds. Tool use can require multiple model requests within a turn.
Complete JSON results are accepted with indentation, line breaks or JSON code
fences, with or without `--verbose`. If a reviewer omits or malforms the required
result record, the host asks that
same reviewer once to correct its format. Both attempts remain in the transcript;
invalid fields or citations still stop the review. Default budgets allow these
corrections (up to eight PR turns or four issue turns); `--max-turns` remains a
hard ceiling. If correction fails, the model has not supplied a complete result
and nothing is posted. Verbose output and transcripts help inspect responses;
neither is required to complete a review.

Every proposed finding must be confirmed, withdrawn with cited evidence, or
reported as unresolved. Approval requires both reviewers to recommend merging,
all seven checks to pass, justified need, no unresolved questions, and no major
or blocker findings. Differing recommendations stay visible in the report.
Each PR report opens and closes with the same verdict: **Ready to merge**,
**Changes requested**, **Hold**, or **Do not merge**. The closing verdict states
whether to merge and gives the approval reason or outstanding requirements.
Rejection takes precedence over requested fixes; a hold means do not merge yet.

Straightforward support or missing-information issues can finish after one
investigation. Other classifications, uncertainty, or an explicit request by
the investigator require one independent verification. Remaining uncertainty is
reported without starting another review loop.

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
| `--dry-run` | Print the report without posting; documentation uses the same architecture freshness and layout gate. |
| `--allow-approve` | Permit a real GitHub approval after all approval gates pass. Otherwise post a comment. |
| `--verbose` | Add the full panel discussion to the default progress output on stderr. |
| `--transcript path.txt` | Save the discussion; a documentation panel uses a sibling `*-pr-N-docs` or `*-issue-N-docs` file. |
| `--workdir path` | Store managed clones, isolated sources and guide worktrees here; defaults to this tool's `repo/`. |
| `--prompts path` | Supply a custom supplementary repository profile. |
| `--timeout seconds` | Timeout for each HTTP attempt; defaults to 180. |
| `--panel-timeout seconds` | Elapsed budget for each PR, issue or documentation panel; defaults to 900. Checked between actions. |
| `--max-turns n` | Override each panel's turn budget. An incomplete panel cannot publish. |

The API key and model also accept `--api-key` and `--llm-model`. Credentials
are not written into session files. See `./code.sh --help` for all options.

Failed model requests, including timeouts, retry up to twice after the initial
attempt, with a fixed 30-second pause before each retry. At the default
180-second HTTP timeout, one exhausted retry sequence can take ten minutes.
Provider compatibility fallbacks can start another sequence. A persistent
HTTP 400 can indicate a rejected request that waiting will not resolve.
Retries preserve completed review turns and apply to PR, issue and documentation
panels. `--panel-timeout` gives each panel a shared 15-minute budget for all its
agents, tool followups, retries and fallbacks. This is cooperative: an in-flight
HTTP attempt and remaining retry pauses can overrun the budget before it is
checked. An exhausted budget or failed request stops the review without posting;
a result returned after expiry is not accepted. There is no deadline for the
entire CLI workflow, including source preparation.

Ctrl+C terminates the CLI immediately, including during native HTTP calls and
retry waits. Existing local review sources and partial transcripts are retained.

Progress uses `[YYYY-MM-DD HH:MM:SS] [model] [agent] [phase]` on stderr,
with local date and time. It identifies preparation, model waits, source reads,
completed turns and final validation. For example:

```text
[2026-09-07 15:30:00] [deepseek-v4-flash] [Lead] [review] waiting for model response (request 1, attempt 1/3 (initial))...
[2026-09-07 15:33:00] [deepseek-v4-flash] [Lead] [review] request 1: retry 1/2 in 30s...
[2026-09-07 15:33:30] [deepseek-v4-flash] [Lead] [review] waiting for model response (request 1, attempt 2/3 (retry 1/2))...
[2026-09-07 15:34:00] [deepseek-v4-flash] [Verifier] [verify] inspecting evidence...
```

Documentation preparation reports `plan`, `draft`, `verify` and `summary`.
Host steps use `Host` as the agent. Normal progress excludes conversation text;
`--verbose` adds the complete agent and system exchanges.
While work is running, a heartbeat is scheduled every 15 seconds to report the
current activity and elapsed time during Git, GitHub and model requests.
Every HTTP attempt shows its logical request number, attempt number and whether
it is the initial attempt or a retry. Compatibility fallbacks keep the request
number and get a separate fallback number. Transport failures show a safe error
category, elapsed time and the next retry pause. Compaction uses phase `compact`.

Before each POST, progress measures the assembled prompt: message count, message
JSON bytes by role, tool-schema count/bytes, total serialized payload JSON bytes,
and a rough token estimate from message/schema JSON characters divided by four.
These include accumulated source reads and tool results. JSON sizes use compact
UTF-8 serialization, not HTTP headers or exact wire size. The token estimate is
not a model tokenizer and may undercount code or non-English text. Numeric input
token usage returned by the provider is logged separately after its response.
These counts do not establish a model's context limit or prove a timeout's cause.
The root and mandatory Agent Rules are already in the topic. Reviewers reuse
those copies and select modules through Task Index paths and reading triggers.
Module bodies and a flattened full-set file inventory are not added to the topic.
Documentation preparation uses a paged metadata tool to locate stale pages before
reading their bodies. This reduces architecture context; it does not establish
a measured wall-clock speedup for live model reviews.

An HTTP response is distinct from a completed review turn. Empty replies and
decoding failures are checked inside kerness; their retries appear on the next
attempt, without a transport-error pause notice. Measurements exclude contents,
URLs and credentials and appear only on stderr, outside the report/transcript.
Heartbeats show both the current activity's elapsed time and total time for the
active step or panel, so evidence reads do not hide the total review duration.
Native provider retry sleeps can delay heartbeat delivery.
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

The latest eatmycode check needs network access on every invocation. It follows
upstream's default-branch HEAD and reads the version and shared rules from its
`SKILL.md`; no pinned release or specification fingerprint gates the run.
A failed fetch or malformed specification stops preflight. A newer version in
any architecture file also stops without changing that file, preventing a
downgrade. Missing, invalid or older stamps trigger content migration against
the fetched skill, and oversized files must be split into linked pages.
Original agent guidance and replaced or removed documents are preserved in
`ARCHITECTURE-ARCHIVE.md` in the local documentation worktree, outside the
coding documentation set.

Model calls can be substantial: a PR includes at most one documentation panel
plus two to four review stages and any format-correction turns. A current doc
set passing mechanical validation skips the documentation panel, worktree
creation and guidance migration. This gate checks versions, per-kind sizes,
layout, exact rules/sections, links and navigation. It does not certify semantic
freshness, source citations or complete subsystem coverage. The PR/issue panel
still inspects full relevant source. Root Task Index has at most eight routes;
index pages have at most twelve, with no navigation cycles.
`tests/test_architecture.py` uses synthetic versions for offline regression
coverage; it is never executed as part of a review.

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
