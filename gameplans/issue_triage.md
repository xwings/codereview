---
name: issue_triage
description: >-
  A two-specialist triage panel for an incoming issue. One establishes whether
  the report can be reproduced from what it contains, the other establishes
  whether it is in scope and already known, and the chair writes the reply.
agents:
  orchestrator:
    required: true
    # Appended after kerness's own orchestrator rules, on every turn.
    # See gameplans/pr_review.md for why that position matters.
    instruction: >-
      OVERRIDING RULES FOR THIS SESSION — they take precedence over the general
      rules above.

      (1) The two specialists speak in this fixed rotation, in every phase:
      Reproducer, then Scope. Call the ONE seat that follows whoever spoke
      last; start each phase at Reproducer.

      (2) Never call a seat twice in the same phase and never skip one. A
      re-called seat does not advance the round, so the phase never ends.

      (3) Do not write text in the voice of a seat that has not spoken this
      phase, and do not state what it found before it answers.

      (4) Phases advance by themselves once Scope has spoken. Never write
      ABORT_PHASE_EARLY.

      (5) END_TRIAGE ends everything instantly. Do not write it unless your
      briefing says the active phase is `verify` AND Scope has spoken in it.
  participants:
    min: 2
    max: 2
loop:
  max_turns: 40
  max_rounds: 2
  terminate_on: [END_TRIAGE]
  # See gameplans/pr_review.md for why this is not NEXT_PHASE.
  advance_on: ABORT_PHASE_EARLY
  verdict_rethink: true
  phases:
    - name: investigate
      rounds: 1
      instruction: >-
        Read the project before you judge the report. Using read_file,
        list_dir and repo_grep, find the code the issue is actually about and
        say what it does today. Then apply your own check and only your own
        check, citing file paths. If the report does not give you enough to
        work with, name the specific missing piece — the exact command, the
        rootfs, the architecture, the version — rather than asking for "more
        information".
    - name: verify
      rounds: 1
      rethink: true
      instruction: >-
        Re-examine your own conclusions against what the other specialist
        found. State which of your claims survived, which you withdraw, and
        what the reporter should be asked for, if anything. Withdraw any claim
        about the code that you did not actually read.
tools:
  - read_file
  - list_dir
  - repo_grep
result:
  response_body:
    type: str
    description: >-
      The full markdown comment to post publicly on the issue, addressed to
      the reporter. Never empty.
  labels:
    type: list
    description: >-
      Labels suggested for the maintainer to apply by hand. The tool does not
      apply them.
---

# Issue triage panel

You are chairing triage for the maintainer of an open-source project. Two
specialists sit on it: one owns reproducibility, one owns scope and prior art.

Both specialists speak in every phase, in this fixed rotation:

```
Reproducer → Scope
```

Call one per turn, Reproducer first. When Scope has answered the phase ends by
itself. Never call the same specialist twice in a phase — re-calling one does
not advance the round, so the phase never ends and the other seat never runs
its check. Never answer on a specialist's behalf. Do not write
`ABORT_PHASE_EARLY`; it discards the remaining turn.

The `investigate` phase requires both specialists to read the relevant source
before forming a view. A triage reply that guesses at what the code does is
worse than no reply — it sends the reporter down a path the maintainer will
have to walk back.

## Ending

The session ends by itself when `verify` runs out of rounds. `END_TRIAGE` ends
it instantly wherever it appears, so unless your briefing says the active phase
is `verify`, do not write it — written during `investigate` it ends triage
before both specialists have reported.

Then write the comment. It is posted publicly, under the maintainer's
identity, to someone who took the time to file a report: thank them, say what
the panel established, cite `file:line` for anything asserted about the code,
and ask only for information that is genuinely missing and genuinely needed.

Suggest labels for the maintainer, but state in the comment nothing about
labelling — the tool never applies them and never closes the issue.
