# harness (gameplans/, personas/, session_builder.py, agent_tools.py)

## Goal

The review panel itself. A gameplan declares the contract — how many agents,
which phases, which tools, what the result must contain — and kerness enforces
it. Personas say who each agent is and, just as importantly, what it must not
comment on. `session_builder.py` binds that declaration to one run;
`agent_tools.py` supplies the three tools the panel may call.

This replaces the old `reviewers/` package, which shelled out to `claude -p`
and `codex exec`. Those are coding harnesses: one model, one pass, no
adversarial check.

## Status

`done` — contract validates offline, all ten personas parse, all three tools
verified against live data.

## Code Structure

| File | Role |
| ---- | ---- |
| `gameplans/pr_review.md` | PR contract: 7 participants + orchestrator, 4 phases, tool list, result schema |
| `gameplans/issue_triage.md` | Issue contract: 2 participants + orchestrator, 2 phases |
| `personas/*.md` | 10 persona files — 7 PR specialists, 2 issue agents, 1 chair |
| `session_builder.py` | provider, channel, access policy, agent/tool registration |
| `agent_tools.py` | `repo_grep`, `package_health`, `github_repo_health` |

## Key Types and Entry Points

- `session_builder.py:38` - `build_provider(api_key, api_base, timeout_s)` - a `kerness.CustomProvider` against any OpenAI-compatible endpoint. **The key is held in memory only** — `session_file=None` means kerness persists nothing, and the key is never logged or written to the transcript.
- `session_builder.py:22` - `PR_PANEL` - seat name → persona file, in the order of the seven checks. The gameplan pins `min: 7, max: 7`, so this tuple and the contract must agree or the session refuses to start.
- **Personas hold no project-specific facts.** A seat's persona says what it owns, how hard to look, and when to withdraw a finding; *what is true of the project under review* arrives only through the topic, from the resolved profile ([prompts.md](prompts.md)). So `security_reviewer.md` names the shape of a trust boundary and points the seat at the architecture notes for where this project's actually is, rather than asserting an emulator's; `style_officer.md` names the four core languages' indents and defers to the measured baseline for everything else. A fact hard-coded into a persona is a fact asserted against every repo, including the ones where it is false.
- `session_builder.py:47` - `_channel(transcript)` - `ConsoleChannel` alone, or wrapped in a `MultiChannel` with a `FileChannel` when `--transcript` is given. `MultiChannel` takes channels as *varargs*, not a list; passing a list makes every delivery raise `AttributeError`, which `MultiChannel._fan_out` catches and logs, so the transcript comes out empty and the run still succeeds. That silent failure is what hid the panel's turn order for the first several debugging runs.
- `session_builder.py:54` - `_build(...)` - `AccessPolicy(workspace=clone, allowed_commands=["*"])`. The workspace is the whole of what the session can touch, and kerness resolves paths itself and rejects `..` traversal and symlink escape, so no path checking is written here. `--transcript` is the one path allowed past it, and the memory path is moved inside it because kerness's default resolves against the launch directory instead.
- `session_builder.py:96` - seat registration. Every agent joins through `session.add_agent(...)`, and which chair it takes is carried by `role=`: the seven specialists name none and are participants, the chair names the built-in `orchestrator` role. kerness resolves `role` at the call, so a typo raises there rather than seating a silent eighth participant.
- `agent_tools.py:60` - `make_repo_grep(clone)` - backed by `git grep` through the audited `git_io.git` chokepoint, so only tracked files match. Capped at `MAX_GREP_LINES = 80`.
- `agent_tools.py:101` - `make_package_health()` - PyPI JSON + OSV.dev advisories (OSV includes GHSA, which matters because `gh api` is deny-listed — see [github-io.md](github-io.md)).
- `agent_tools.py:180` - `make_github_repo_health()` - `gh repo view --json`, so it inherits the deny-list.

### The four phases

| Phase | Rounds | What happens |
| ----- | ------ | ------------ |
| `study_repo` | 1 | Read the project *before* the diff. Each specialist establishes the existing baseline in its own area. This is half of check 5 and the evidence base for 1, 2, 3. |
| `review_pr` | 1 | Each specialist runs its own check against the diff and the checkout. |
| `cross_check` | 1 | Challenge another specialist's finding; retract your own when the challenge lands. |
| `verify` | 1, `rethink: true` | Re-walk checks 1–7 in order and mark every finding CONFIRMED or WITHDRAWN with the evidence that settled it. |

A "round" in kerness means every participant has spoken once, and a phase's
`rounds` is clamped to `loop.max_rounds` — hence `max_rounds: 4` for four
phases of one round each. `verdict_rethink: true` adds the orchestrator's
second pass over its own draft.

### Why the chair drives the rotation, and how it used to fail

Nothing in this repository makes the seven seats take their turns. The
orchestrator loop does, and until the kerness fixes described below it did not:
across six end-to-end runs against PR 1630 the chair never got the panel out of
`study_repo`. It re-called seats that had already spoken, never closed a round,
and then wrote the un-called specialists' contributions in their own voice —

```
[Chair] @Naming, study the repository's naming conventions ...
[Naming] ...
[Chair] [Security] Final seven-check walk:        <-- chair, in Security's voice
        ... Duplication: pass. Quality: pass. Dependencies: pass. Security: pass.
```

— so the run ended with a confident seven-check "all pass" verdict for checks
that had never run. `gpt-5.6-sol` was tried on the premise that a stronger chair
would hold the roster. It does not: the better model writes accurate `file:line`
citations and well-argued findings into the seats it never called. Model choice
changes the quality of the fabrication, not the shape of the failure.

Three kerness defects caused it, none of them reachable from a gameplan. All
three are fixed on kerness's `dev` branch, which is what `requirements.txt`
now points at:

1. **The roster was only refreshed at phase boundaries.** `brief()` ran at the
   start, on early advance, and after a round closed — never before an ordinary
   orchestrator turn. Between boundaries `pending` shrinks with every
   participant who speaks, so the chair was reading a stale roster and re-called
   someone already heard from; `record_turn` clears only a name still pending,
   so the round never closed, so the next boundary — the only thing that would
   have corrected the briefing — never arrived. Self-sustaining, and the code
   comment at `orchestrator.rs:249` predicted it exactly. The fix carries the
   briefing into *every* orchestrator turn as a transient instruction, the same
   channel `turn_instruction` already used to put the phase requirement in front
   of every participant.
2. **kerness's own rules block contradicted the gameplan.** Every orchestrator
   turn carried "You control the flow: decide who speaks, *when to move
   phases*, when to summarize" and "You can *summarize* ... at any point" —
   fine for a three-agent debate, wrong for a phased panel, and in the same
   system prompt as anything this repo writes. The fix drops that licence when
   the harness declares phases and replaces it with "the phases advance on their
   own" plus an explicit "never write a participant's turn for them".
3. **The re-ask after an unparseable reply named nobody.** With 1 and 2 fixed
   the chair reached the seventh seat and then wrote Security's turn itself; the
   reply routed to no one, and the generic "reply with an @Name" hint drew the
   same text twice more before the retry budget forced the session to end — one
   turn short of closing its first round. The hint now names the head of the
   pending set outright.

`review.py:336` `require_completed_panel` is the containment that made all of
this safe to debug: a panel that did not reach `verify` cannot post, so every
failed run was loud and local instead of a fabricated approval on a public PR.
It fired on all six.

With the three fixes the same PR runs the panel it claims to: **62 turns, 4
rounds, last phase `verify`, ended `phases_complete`**, with all seven seats
speaking in each of the four phases.

### Why `advance_on` is `ABORT_PHASE_EARLY`

Phases advance on their own: `record_turn` (`orchestrator.rs:284`) closes a
round when the last participant clears `pending`, and closing the round
advances the phase. The chair never needs to advance one by hand.

But kerness always installs an early-advance keyword and always tells the
orchestrator about it — the briefing at `orchestrator.rs:273` reads "Write
`<keyword>` to move to the next phase before its rounds are up" — and it cannot
be switched off, because an empty `advance_on` re-defaults to `NEXT_PHASE`
(`harness.rs:494`). **The first end-to-end run failed on exactly this:** with
the keyword named `NEXT_PHASE`, the chair emitted it as a progress marker after
one or two specialists had spoken, ran the whole review in 8 turns instead of
~28, and then wrote summaries in the missing specialists' names. Six of the
seven checks were never performed, and the posted body said all seven passed.

So the keyword is renamed to something no chair emits as punctuation, and the
gameplan body ties the rule to the briefing's own machine-generated `Yet to
speak this round:` line. `terminate_on` has the same failure mode — an early
`END_REVIEW` ends the session just as effectively — and gets the same
treatment: the chair is told the session ends by itself on phase exhaustion
(`EndReason::PhasesComplete`, `orchestrator.rs:556`), so the keyword is a
last-turn affordance rather than a progress marker.

**Check `turns_completed` on every run.** `review.py` prints it. A PR review
that finishes in far fewer than ~28 participant turns did not run the panel it
claims to have run — see the rotation section above for what that looked like
when it was the normal outcome.

### Sandbox posture

Hard guardrail 3 ("no tests are executed") is structural here, not a
convention. kerness's tool resolution *narrows*: a tool absent from the
gameplan's `tools:` list is unreachable to every agent. `cmd` is deliberately
never listed, so there is no path from PR content to a subprocess — and that,
not the access policy, is what holds: `allowed_commands=["*"]` would admit any
command line an agent could reach, and no agent can reach one. The remaining
reach is `read_file`/`list_dir` confined to the checkout, plus the three tools
above.

## Interactions

- Built and run by [review-cli.md](review-cli.md).
- Reads the checkout prepared by [git-io.md](git-io.md).
- `github_repo_health` goes through [github-io.md](github-io.md).
- Consumes the reference material described in [prompts.md](prompts.md).

## How to Test

```sh
.venv/bin/python -m kerness.selfcheck         # pass = "OK: all core checks passed"
.venv/bin/python - <<'EOF'   # pass = "contract OK" then "negative test OK: SessionError"
import tempfile
from pathlib import Path
import kerness, session_builder
prov = session_builder.build_provider("dummy", "http://127.0.0.1:1/v1", 5)
clone = Path(tempfile.mkdtemp())      # any checkout will do; no repo is special
session_builder.build_pr_session(topic="t", clone=clone, provider=prov,
                                 model="m", transcript=None, max_turns=None)
session_builder.build_issue_session(topic="t", clone=clone, provider=prov,
                                    model="m", transcript=None, max_turns=None)
print("contract OK")
try:                                    # too few participants must be rejected
    bad = kerness.Session(gameplan="gameplans/pr_review.md", topic="t", provider=prov,
                          channel=kerness.ConsoleChannel(), session_file=None,
                          memory=str(clone.resolve() / "memory.md"),
                          access_policy=kerness.AccessPolicy(workspace=str(clone.resolve())))
    bad.add_agent("Only", model="m", persona="personas/style_officer.md")
    bad.add_agent("Chair", model="m", persona="personas/maintainer_chair.md",
                  role="orchestrator")
    bad.run()
    print("FAIL: 1 participant accepted")
except Exception as e:
    print("negative test OK:", type(e).__name__)
EOF
grep -c '^\s*- cmd' gameplans/pr_review.md; test $? -ne 0 && echo "ok no cmd tool"
# That no persona names a project is guarded repo-wide in review-cli.md. This is
# the positive half: pass = >= 2 — the seats whose scope depends on what the
# project *is* (security_reviewer, issue_reproducer) are pointed at the topic's
# architecture notes rather than told. Either may name a project *shape*
# ("an emulator", "a parser") as one alternative among several; asserted as the
# shape of the repo in hand, it is a finding.
grep -rn 'read the architecture notes\|architecture notes in your topic' personas/ | wc -l
```

Contract validation happens in `Session.__init__`/`run` *before* any provider
call, so both checks above run offline with a dummy key.

## Open Gaps / Roadmap

- Cost: 8 agents × 4 phases ≈ 28 participant turns, each preceded by an
  orchestrator turn — roughly 60 model calls per PR against a growing
  transcript. `--max-turns` and the 60 KB inline diff budget are the levers.
- Prompt injection via PR text still reaches the model. Mitigations are the
  absent `cmd` tool, the confining workspace, the `--allow-approve` gate,
  and the maintainer reading the posted body.
- A specialist that finds nothing still spends its turns. Skipping idle seats
  after `study_repo` would cut cost but is not implemented.
