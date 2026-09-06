# Workflow and launcher

## Goal

Coordinate documentation-first PR review and issue triage (M1–M3), while
keeping model orchestration, report policy and I/O in their owning modules.

## Status

`done` — offline workflow tests and launcher checks pass. Live model quality
and GitHub posting require configured credentials and are separate smoke checks.

## Code Structure

| File | Role |
| ---- | ---- |
| `review.py` | Arguments, profile resolution, topics and workflow coordination |
| `code.sh` | Select the project virtual environment and forward arguments |
| `repo_facts.py` | Measured indentation, new symbols and manifest changes |
| `tests/test_workflow.py` | Workflow, real scripted panels, report and GitHub behavior |

## Key Types and Entry Points

- `review.py:76` — `parse_args`: `--id NUMBER` for automatic PR/issue detection,
  required repository and model credentials. Legacy `auto|pr|issue NUMBER`
  also works, but cannot be mixed with `--id`. Relative caller paths stay relative.
- `review.py:185` — `resolve_base_branch`: explicit flag, PR base, profile pin,
  then GitHub default. Initial documentation and issue triage have no PR base.
- `review.py:251` — `build_pr_topic`: audited architecture, supplementary
  profile, rubric, style reference, measured facts, PR metadata and pinned diff.
- `review.py:303` — `build_issue_topic`: architecture, source context and issue.
- `review.py:339` — `prepare_docs`: make a retained documentation worktree and
  run the documentation panel; never modify the original review source.
- `review.py:375` — `handle_pr`: fresh branch, pinned head/diff, original source
  worktree, PR-specific docs, panel, validated report and final head/state check.
- `review.py:415` — `handle_issue`: original baseline source and separate guide,
  triage panel, cited response and optional suggested labels on stderr.
- `review.py:429` — `main`: latest eatmycode and baseline documentation before
  routing. Explicit kind mismatch stops without posting.
- `repo_facts.py:136` — `collect`: deterministic leads for style, duplication and
  dependency reviewers; these regex-based measurements are not verdicts.
- `code.sh:4` — launcher resolves itself, prefers `.venv`, falls back to `venv`,
  forwards each argument unchanged and preserves exit status.
  It directly executes Python, with no output capture, filtering or formatting.

## Interactions

[Architecture preflight](architecture-preflight.md) prepares the guide.
[Git](git-io.md) owns worktrees and revision consistency; [GitHub](github-io.md)
owns resource detection and publication. [Harness](harness.md) returns strict
results; [reporting](reporting.md) decides approval eligibility and renders it.
[Profiles](prompts.md) supplement the source's facts.

## How to Test

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile review.py repo_facts.py
./code.sh --help
```

Expected: all tests pass, compile exits 0, help includes `--id`, `--verbose`,
`--dry-run` and `--allow-approve`. Stdout from a review contains only Markdown;
progress and suggested labels go to stderr. The scripted integration tests
use the real kerness engine, without network model calls or GitHub writes.

## Open Gaps / Roadmap

- Documentation is audited on both baseline and PR head, adding model calls.
- `--timeout` is per request; there is no whole-run wall-clock budget.
- Source and guide worktrees are retained for inspection and require cleanup.
- Python, C, C++ and Rust have measured style/symbol leads. Other languages
  rely on source inspection; no new language coverage is claimed.
- GitHub posting is not exercised by offline tests. Use `--dry-run` for the
  first configured live model run.
